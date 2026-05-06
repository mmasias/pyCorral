#!/bin/bash

# pyCorral Setup Script
# Automatiza la instalación de servidores MCP para orquestación de agentes.

set -e

echo "--- pyCorral Setup ---"

# 1. Verificar dependencias básicas
echo "[1/9] Verificando Python 3 y pip3..."
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 no está instalado."
    echo "Instálalo con:"
    echo "  Debian/Ubuntu: sudo apt install python3"
    echo "  Fedora: sudo dnf install python3"
    echo "  macOS: brew install python3"
    exit 1
fi

if ! command -v pip3 &> /dev/null; then
    echo "Error: pip3 no está instalado."
    echo "Instálalo con:"
    echo "  Debian/Ubuntu: sudo apt install python3-pip"
    echo "  Fedora: sudo dnf install python3-pip"
    exit 1
fi

# 2. Instalar librería MCP
echo "[2/9] Instalando dependencia 'mcp'..."
pip3 install mcp --break-system-packages 2>/dev/null || pip3 install mcp

# 3. Detectar CLIs de agentes
echo "[3/9] Detectando gemini y opencode..."
GEMINI_PATH=$(which gemini || true)
OPENCODE_PATH=$(which opencode || true)

if [ -z "$GEMINI_PATH" ]; then
    echo "Aviso: gemini CLI no encontrado. Deberás instalarlo para usar el servidor gemini."
else
    echo "  Gemini encontrado en: $GEMINI_PATH"
fi

if [ -z "$OPENCODE_PATH" ]; then
    echo "Aviso: opencode CLI no encontrado. Deberás instalarlo para usar el servidor opencode."
else
    echo "  OpenCode encontrado en: $OPENCODE_PATH"
fi

# 4. Preparar directorios de instalación
echo "[4/9] Creando ~/mcp-servers/ y ~/misRepos/corral/..."
mkdir -p ~/mcp-servers
mkdir -p ~/misRepos/corral/gemini
mkdir -p ~/misRepos/corral/opencode

# 5. Copiar scripts
echo "[5/9] Copiando scripts desde servers/..."
cp servers/gemini_mcp.py ~/mcp-servers/
cp servers/opencode_mcp.py ~/mcp-servers/
cp servers/opencode-wrapper.sh ~/mcp-servers/
chmod +x ~/mcp-servers/opencode-wrapper.sh
echo "  Scripts copiados a ~/mcp-servers/"

# 6. Configurar modelo de OpenCode
echo "[6/9] Configurando modelo para OpenCode..."
if [ -n "$OPENCODE_PATH" ]; then
    echo "Modelos disponibles (zai):"
    opencode models 2>/dev/null | grep "^zai" || echo "  No se pudieron listar modelos (¿estás autenticado?)"
    
    DEFAULT_MODEL="opencode/big-pickle"
    read -p "Introduce el modelo de OpenCode a usar [$DEFAULT_MODEL]: " SELECTED_MODEL
    SELECTED_MODEL=${SELECTED_MODEL:-$DEFAULT_MODEL}
    
    EXPORT_LINE="export CORRAL_OPENCODE_MODEL=\"$SELECTED_MODEL\""
    
    # Añadir a .bashrc
    if [ -f "$HOME/.bashrc" ]; then
        if ! grep -q "CORRAL_OPENCODE_MODEL" "$HOME/.bashrc"; then
            echo "$EXPORT_LINE" >> "$HOME/.bashrc"
            echo "  Añadido a ~/.bashrc"
        else
            sed -i "s|export CORRAL_OPENCODE_MODEL=.*|$EXPORT_LINE|" "$HOME/.bashrc"
            echo "  Actualizado en ~/.bashrc"
        fi
    fi
    
    # Añadir a .zshrc
    if [ -f "$HOME/.zshrc" ]; then
        if ! grep -q "CORRAL_OPENCODE_MODEL" "$HOME/.zshrc"; then
            echo "$EXPORT_LINE" >> "$HOME/.zshrc"
            echo "  Añadido a ~/.zshrc"
        else
            sed -i "s|export CORRAL_OPENCODE_MODEL=.*|$EXPORT_LINE|" "$HOME/.zshrc"
            echo "  Actualizado en ~/.zshrc"
        fi
    fi
    
    export CORRAL_OPENCODE_MODEL="$SELECTED_MODEL"
fi

# 7. Mostrar bloque de permisos para Claude Code
echo "[7/9] Configuración de permisos para Claude Code..."
echo "Asegúrate de que ~/.claude/settings.json incluya lo siguiente:"
cat <<EOF

{
  "permissions": {
    "allow": [
      "mcp__gemini__*",
      "mcp__opencode__*"
    ]
  }
}

EOF

# 8. Registrar servidores en Claude Code
echo "[8/9] Registrando servidores en Claude Code..."
if command -v claude &> /dev/null; then
    claude mcp add gemini --scope user -- python3 "$HOME/mcp-servers/gemini_mcp.py"
    claude mcp add opencode --scope user -- python3 "$HOME/mcp-servers/opencode_mcp.py"
else
    echo "Aviso: no se encontró el comando 'claude'. Regístralos manualmente más tarde:"
    echo "  claude mcp add gemini --scope user -- python3 ~/mcp-servers/gemini_mcp.py"
    echo "  claude mcp add opencode --scope user -- python3 ~/mcp-servers/opencode_mcp.py"
fi

# 9. Finalización
echo "[9/9] ¡Instalación completada!"
echo ""
echo "Próximos pasos:"
echo "1. Reinicia tu terminal o ejecuta: source ~/.bashrc (o ~/.zshrc)"
echo "2. Verifica los servidores con: claude mcp list"
echo "3. Prueba un comando: claude 'Usa la herramienta gemini_run para crear un hola.txt en /tmp/test'"
echo ""
echo "Para más detalles, consulta el README.md."
