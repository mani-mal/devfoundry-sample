#!/usr/bin/env bash
set -euo pipefail

DATABASE_URL="${1:-${DATABASE_URL:-}}"
if [ -z "$DATABASE_URL" ]; then
  echo "Usage: $0 <database_url>  (or set DATABASE_URL)" >&2
  exit 1
fi

MIGRATIONS_DIR="$(cd "$(dirname "$0")/../migrations" && pwd)"

if command -v psql >/dev/null 2>&1; then
  PSQL=(psql)
elif command -v docker >/dev/null 2>&1 && docker ps --filter name=equipflow-pg --format '{{.Names}}' | grep -q '^equipflow-pg$'; then
  PSQL=(docker exec -i equipflow-pg psql)
elif [ -x "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" ] && "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" ps --filter name=equipflow-pg --format '{{.Names}}' 2>/dev/null | grep -q '^equipflow-pg$'; then
  PSQL=("/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" exec -i equipflow-pg psql)
else
  echo "psql not found and equipflow-pg container not running" >&2
  exit 1
fi

if [ "${PSQL[0]}" != "psql" ]; then
  DATABASE_URL="${DATABASE_URL/localhost:5433/localhost:5432}"
fi

"${PSQL[@]}" "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "CREATE TABLE IF NOT EXISTS schema_migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT NOW());"

shopt -s nullglob
for file in $(ls "$MIGRATIONS_DIR"/*.sql | sort); do
  base="$(basename "$file")"
  applied=$("${PSQL[@]}" "$DATABASE_URL" -tA -c "SELECT 1 FROM schema_migrations WHERE filename = '$base';")
  if [ "$applied" = "1" ]; then
    echo "skip  $base"
    continue
  fi
  echo "apply $base"
  {
    echo "BEGIN;"
    echo "INSERT INTO schema_migrations (filename) VALUES ('$base');"
    cat "$file"
    echo "COMMIT;"
  } | "${PSQL[@]}" "$DATABASE_URL" -v ON_ERROR_STOP=1 -f -
done

echo "migrations complete"
