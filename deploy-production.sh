#!/usr/bin/env bash
set -euo pipefail

# First deployment or update of Activities behind the shared Traefik proxy.
# Run from the repository root after .env is configured.
cd "$(dirname "$0")"

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

if [ ! -f .env ]; then
  echo "Chybi .env. Zkopirujte .env.example a nastavte produkcni hesla." >&2
  exit 1
fi

if ! grep -qE '^DOMAIN=activities\.sevcikassets\.cz$' .env; then
  echo "V .env musi byt DOMAIN=activities.sevcikassets.cz." >&2
  exit 1
fi

if ! docker network inspect proxy >/dev/null 2>&1; then
  echo "Chybi sdilena Docker sit proxy. Nejprve spustte centralni Traefik proxy." >&2
  exit 1
fi

mkdir -p uploads exports

echo "==> Sestavuji image aplikace..."
"${COMPOSE[@]}" build

echo "==> Spoustim PostgreSQL..."
"${COMPOSE[@]}" up -d db

echo "==> Spoustim API a web..."
"${COMPOSE[@]}" up -d api web

echo "==> Kontroluji API..."
for attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
    break
  fi
  if [ "$attempt" = 30 ]; then
    echo "API neodpovida na localhost:8000." >&2
    "${COMPOSE[@]}" logs --tail=100 api >&2 || true
    exit 1
  fi
  sleep 2
done

echo "==> Nasazeni dokonceno."
"${COMPOSE[@]}" ps
