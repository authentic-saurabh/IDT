#!/usr/bin/env bash
set -euo pipefail

docker compose up -d prometheus grafana backend
(
  cd backend
  python3 -m uvicorn app:app --host 0.0.0.0 --port 8000
) &
(
  cd frontend
  npm install
  npm run dev -- --host 0.0.0.0
) &
wait
