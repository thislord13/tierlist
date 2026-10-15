#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv-linux"
cd "$PROJECT_DIR"

if command -v uv >/dev/null 2>&1; then
    UV_BIN="$(command -v uv)"
elif [[ -x "$HOME/.local/bin/uv" ]]; then
    UV_BIN="$HOME/.local/bin/uv"
else
    if ! command -v curl >/dev/null 2>&1; then
        echo "Erro: instale curl e execute este script novamente."
        exit 1
    fi
    echo "Instalando uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    UV_BIN="$HOME/.local/bin/uv"
fi

if [[ ! -x "$UV_BIN" ]]; then
    echo "Erro: nao foi possivel localizar o uv apos a instalacao."
    exit 1
fi

echo "Baixando Python 3.13..."
"$UV_BIN" python install 3.13

echo "Aguardando 1 minuto..."
sleep 60

echo "Criando ambiente virtual com Python 3.13..."
"$UV_BIN" venv --python 3.13 "$VENV_DIR"

echo "Instalando dependencias do requirements.txt..."
"$UV_BIN" pip install --python "$VENV_DIR/bin/python" -r "$PROJECT_DIR/requirements.txt"

echo "Iniciando o site..."
exec "$VENV_DIR/bin/python" "$PROJECT_DIR/app.py"