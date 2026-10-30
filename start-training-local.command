#!/bin/zsh
set -eu
cd "${0:A:h}"
export LIFE_REPLAY_DB="$PWD/backend/training-local.sqlite3"
export LIFE_EMAIL_MODE=development LIFE_DEVELOPMENT_MODE=1
# AI uses private backend/ai-config.json; optional environment flags can disable it.
export LIFE_AI_BASE_URL='' LIFE_AI_API_KEY=''
./backend/.venv/bin/python - <<'PY'
import socket,sys
for port in (8010,5180):
 with socket.socket() as s:
  if s.connect_ex(('127.0.0.1',port))==0:sys.exit(f'本機 {port} 正在使用。若訓練服務已啟動，可直接開啟 http://127.0.0.1:5180/training')
PY
api_pid='';ui_pid='';tail_pid=''
trap '[[ -n "$api_pid" ]] && kill "$api_pid" 2>/dev/null || true; [[ -n "$ui_pid" ]] && kill "$ui_pid" 2>/dev/null || true; [[ -n "$tail_pid" ]] && kill "$tail_pid" 2>/dev/null || true' EXIT INT TERM
(cd backend; exec .venv/bin/python -m app.main --host 127.0.0.1 --port 8010) &
api_pid=$!
./backend/.venv/bin/python life-reroll-frontend-20261016-212920/serve.py --host 127.0.0.1 --port 5180 --api-proxy http://127.0.0.1:8010 &
ui_pid=$!
if ./backend/.venv/bin/python scripts/training-tailscale.py --check >/dev/null 2>&1; then
  ./backend/.venv/bin/python scripts/training-tailscale.py &
  tail_pid=$!
else
  print 'Tailscale 尚未就緒，先提供本機入口。連線後可再執行 start-training-tailscale.command。'
fi
print '學員：http://127.0.0.1:5180/training　講師：http://127.0.0.1:5180/teach'
print 'AI 依 backend/ai-config.json 設定。Ctrl-C 停止本次啟動的兩個程序。'
wait
