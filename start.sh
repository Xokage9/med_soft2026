#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")"

PY=.venv/bin/python

if [ ! -x "$PY" ]; then
  BASE=""
  for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1 \
       && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
      BASE="$candidate"
      break
    fi
  done
  if [ -z "$BASE" ]; then
    echo "Нужен Python 3.10 или новее: brew install python@3.12"
    exit 1
  fi
  echo "Создаю окружение (.venv) на $($BASE --version)..."
  "$BASE" -m venv .venv
  "$PY" -m pip install -q --upgrade pip
  "$PY" -m pip install -q -r requirements.txt
fi

if [ ! -f certs/server.key ]; then
  "$PY" tools/make_certs.py --force
  echo
  echo "Добавьте учебный CA в доверенные (один раз, macOS спросит пароль):"
  echo "  security add-trusted-cert -r trustRoot -k ~/Library/Keychains/login.keychain-db certs/ca.crt"
  echo
fi

"$PY" -m server &
API_PID=$!
"$PY" client/serve.py &
CLIENT_PID=$!
trap 'kill $API_PID $CLIENT_PID 2>/dev/null; exit 0' INT TERM EXIT

sleep 2
open "https://localhost:8444/" 2>/dev/null || xdg-open "https://localhost:8444/" 2>/dev/null || true
echo "Работает. Остановить: Ctrl+C"
wait
