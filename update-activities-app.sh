#!/usr/bin/env bash
set -euo pipefail

# Update a running production instance from origin/master.
cd "$(dirname "$0")"
BRANCH="master"

echo "==> Kontroluji nove commity na origin/$BRANCH..."
git fetch origin "$BRANCH"
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")

if [ "$LOCAL" = "$REMOTE" ]; then
  echo "==> Zadna nova zmena, appka je aktualni (${LOCAL:0:7})."
  exit 0
fi

echo "==> Commity, ktere se nasadi:"
git log --oneline --reverse "$LOCAL..$REMOTE"
git pull --ff-only origin "$BRANCH"

COMPOSE=(docker compose -f docker-compose.yml)
if [ -f .env ] && grep -qE '^DOMAIN=activities\.sevcikassets\.cz$' .env; then
  COMPOSE+=(-f docker-compose.prod.yml)
  echo "==> Aktualizuji aplikaci za sdilenym Traefik proxy..."
else
  echo "==> Aktualizuji aplikaci bez produkcniho proxy overlay..."
fi

"${COMPOSE[@]}" up -d --build

echo
echo "==> Hotovo. Bezi:"
"${COMPOSE[@]}" ps
