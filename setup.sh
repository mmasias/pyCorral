#!/bin/bash

# pyCorral Setup Script
# Automatiza la instalación de servidores MCP para orquestación de agentes.

set -e

echo "--- pyCorral Setup ---"

# 1. Verificar dependencias básicas
echo "[1/10] Verificando Python 3 y pip3..."
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
echo "[2/10] Instalando dependencia 'mcp'..."
pip3 install mcp --break-system-packages 2>/dev/null || pip3 install mcp

# 3. Detectar CLIs de agentes
echo "[3/10] Detectando gemini, opencode, ollama y kiro..."
GEMINI_PATH=$(which gemini 2>/dev/null || true)
OPENCODE_PATH=$(which opencode 2>/dev/null || true)
OLLAMA_PATH=$(which ollama 2>/dev/null || true)
KIRO_PATH=$(which kiro-cli-chat 2>/dev/null || true)

if [ -z "$GEMINI_PATH" ]; then
    echo "  Aviso: gemini CLI no encontrado. Deberás instalarlo para usar el servidor gemini."
else
    echo "  Gemini encontrado en: $GEMINI_PATH"
fi

if [ -z "$OPENCODE_PATH" ]; then
    echo "  Aviso: opencode CLI no encontrado. Deberás instalarlo para usar el servidor opencode."
else
    echo "  OpenCode encontrado en: $OPENCODE_PATH"
fi

if [ -z "$OLLAMA_PATH" ]; then
    echo "  Aviso: ollama no encontrado. El servidor ollama_mcp.py se copiará pero no estará activo."
else
    echo "  Ollama encontrado en: $OLLAMA_PATH"
fi

if [ -z "$KIRO_PATH" ]; then
    echo "  Aviso: kiro-cli-chat no encontrado. El servidor kiro_mcp.py se copiará pero no estará activo."
else
    echo "  Kiro encontrado en: $KIRO_PATH"
fi

# 4. Preparar directorios
echo "[4/10] Creando ~/mcp-servers/ y directorios de trabajo CORRAL..."
mkdir -p ~/mcp-servers
mkdir -p ~/misRepos/corral/gemini \
         ~/misRepos/corral/opencode \
         ~/misRepos/corral/ollama \
         ~/misRepos/corral/kiro \
         ~/misRepos/corral/tasks

# 5. Copiar scripts
echo "[5/10] Copiando scripts desde servers/..."
cp servers/gemini_mcp.py ~/mcp-servers/
cp servers/opencode_mcp.py ~/mcp-servers/
cp servers/opencode-wrapper.sh ~/mcp-servers/
cp servers/ollama_mcp.py ~/mcp-servers/
cp servers/kiro_mcp.py ~/mcp-servers/
chmod +x ~/mcp-servers/opencode-wrapper.sh
echo "  Scripts copiados a ~/mcp-servers/"

# 6. Configurar modelo de OpenCode
echo "[6/10] Configurando modelo para OpenCode..."
if [ -n "$OPENCODE_PATH" ]; then
    echo "  Modelos disponibles:"
    opencode models 2>/dev/null || echo "  No se pudieron listar modelos (¿estás autenticado?)"

    DEFAULT_MODEL="openai/gpt-4o"
    read -p "  Introduce el modelo de OpenCode a usar [$DEFAULT_MODEL]: " SELECTED_MODEL
    SELECTED_MODEL=${SELECTED_MODEL:-$DEFAULT_MODEL}

    EXPORT_LINE="export CORRAL_OPENCODE_MODEL=\"$SELECTED_MODEL\""

    if [ -f "$HOME/.bashrc" ]; then
        if ! grep -q "CORRAL_OPENCODE_MODEL" "$HOME/.bashrc"; then
            echo "$EXPORT_LINE" >> "$HOME/.bashrc"
            echo "  Añadido a ~/.bashrc"
        else
            sed -i "s|export CORRAL_OPENCODE_MODEL=.*|$EXPORT_LINE|" "$HOME/.bashrc"
            echo "  Actualizado en ~/.bashrc"
        fi
    fi

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

# 7. Configurar modelo de Ollama
echo "[7/10] Configurando modelo para Ollama..."
if [ -n "$OLLAMA_PATH" ]; then
    echo "  Modelos Ollama instalados:"
    ollama list 2>/dev/null || echo "  No se pudieron listar modelos (¿está corriendo el servicio ollama?)"

    DEFAULT_OLLAMA_MODEL="qwen2.5:7b"
    read -p "  Introduce el modelo de Ollama a usar [$DEFAULT_OLLAMA_MODEL]: " OLLAMA_MODEL
    OLLAMA_MODEL=${OLLAMA_MODEL:-$DEFAULT_OLLAMA_MODEL}

    OLLAMA_EXPORT="export CORRAL_OLLAMA_MODEL=\"$OLLAMA_MODEL\""

    if [ -f "$HOME/.bashrc" ]; then
        if ! grep -q "CORRAL_OLLAMA_MODEL" "$HOME/.bashrc"; then
            echo "$OLLAMA_EXPORT" >> "$HOME/.bashrc"
            echo "  Añadido a ~/.bashrc"
        else
            sed -i "s|export CORRAL_OLLAMA_MODEL=.*|$OLLAMA_EXPORT|" "$HOME/.bashrc"
            echo "  Actualizado en ~/.bashrc"
        fi
    fi

    if [ -f "$HOME/.zshrc" ]; then
        if ! grep -q "CORRAL_OLLAMA_MODEL" "$HOME/.zshrc"; then
            echo "$OLLAMA_EXPORT" >> "$HOME/.zshrc"
            echo "  Añadido a ~/.zshrc"
        else
            sed -i "s|export CORRAL_OLLAMA_MODEL=.*|$OLLAMA_EXPORT|" "$HOME/.zshrc"
            echo "  Actualizado en ~/.zshrc"
        fi
    fi

    export CORRAL_OLLAMA_MODEL="$OLLAMA_MODEL"
    echo "  CORRAL_OLLAMA_MODEL=$OLLAMA_MODEL configurado."
fi

# 8. Verificar Kiro
echo "[8/10] Verificando Kiro..."
if [ -n "$KIRO_PATH" ]; then
    KIRO_VERSION=$("$KIRO_PATH" --version 2>/dev/null || echo "desconocida")
    echo "  kiro-cli-chat operativo. Versión: $KIRO_VERSION"
else
    echo "  Aviso: kiro-cli-chat no encontrado en PATH."
    echo "  Instala Kiro desde: https://kiro.dev"
    echo "  El servidor kiro_mcp.py quedará instalado pero inactivo hasta que esté disponible."
fi

# 9. Mostrar bloque de permisos para Claude Code
echo "[9/10] Configuración de permisos para Claude Code..."
echo "  Asegúrate de que ~/.claude/settings.json incluya lo siguiente:"
cat <<EOF

{
  "permissions": {
    "allow": [
      "mcp__gemini__*",
      "mcp__opencode__*",
      "mcp__ollama__*",
      "mcp__kiro__*"
    ]
  }
}

EOF

# 10. Registrar servidores en Claude Code
echo "[10/10] Registrando servidores en Claude Code..."
if command -v claude &> /dev/null; then
    claude mcp add gemini --scope user -- python3 "$HOME/mcp-servers/gemini_mcp.py"
    claude mcp add opencode --scope user -- python3 "$HOME/mcp-servers/opencode_mcp.py"
    claude mcp add ollama --scope user -- python3 "$HOME/mcp-servers/ollama_mcp.py"
    claude mcp add kiro --scope user -- python3 "$HOME/mcp-servers/kiro_mcp.py"
else
    echo "  Aviso: no se encontró el comando 'claude'. Regístralos manualmente:"
    echo "  claude mcp add gemini --scope user -- python3 ~/mcp-servers/gemini_mcp.py"
    echo "  claude mcp add opencode --scope user -- python3 ~/mcp-servers/opencode_mcp.py"
    echo "  claude mcp add ollama --scope user -- python3 ~/mcp-servers/ollama_mcp.py"
    echo "  claude mcp add kiro --scope user -- python3 ~/mcp-servers/kiro_mcp.py"
fi

# Finalización
echo ""
echo "--- Instalación completada ---"
echo ""
echo "Próximos pasos:"
echo "1. Reinicia tu terminal o ejecuta: source ~/.bashrc (o ~/.zshrc)"
echo "2. Verifica los servidores con: claude mcp list"
echo "3. Prueba un agente: claude 'Usa gemini_run para escribir hola.txt en /tmp/test'"
echo ""
echo "Para más detalles, consulta el README.md."
