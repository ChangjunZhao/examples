#!/usr/bin/env bash
# Generate secrets, bring the stack up, and issue an E2B-shaped API key.
set -euo pipefail
cd "$(dirname "$0")"

: "${SANDRPOD_DOMAIN:?set SANDRPOD_DOMAIN}"

if [ ! -f .env ]; then
  umask 077
  cat > .env <<ENV
SANDRPOD_DOMAIN=$SANDRPOD_DOMAIN
SANDRPOD_TOKEN=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -hex 16)
ENV
  echo "==> wrote .env (mode $(stat -c %a .env))"
fi
set -a; source .env; set +a

docker compose up -d --wait

# The admin API is bound to loopback: once SANDRPOD_E2B_DOMAIN is set, every
# host under that domain belongs to the E2B gateway and /api/v1/* 404s there.
KEY=$(curl -s -X POST -H "Authorization: Bearer $SANDRPOD_TOKEN" \
  -H 'Content-Type: application/json' -d '{"name":"demo","role":"user"}' \
  http://127.0.0.1:8080/api/v1/tokens | python3 -c 'import sys,json;print(json.load(sys.stdin)["key"])')

grep -q '^E2B_API_KEY=' .env || echo "E2B_API_KEY=$KEY" >> .env
echo
echo "==> point the unmodified E2B SDK at it:"
echo "    export E2B_DOMAIN=$SANDRPOD_DOMAIN"
echo "    export E2B_API_KEY=$KEY"
