#!/usr/bin/env bash
# Install SearXNG natively, without Docker, bound to loopback.
#
# SearXNG is AGPL-3.0. It runs as its own process and is never imported by this project, which
# keeps that licence off our code. Queries go to your instance, which fans them out - the search
# engines see SearXNG, not you.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIR="${ROOT}/services/searxng"
PORT="${SEARXNG_PORT:-8888}"

command -v git >/dev/null || { echo "git is required"; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }

mkdir -p "${DIR}"
if [ ! -d "${DIR}/src/.git" ]; then
  echo "Cloning SearXNG into ${DIR}/src ..."
  git clone --depth 1 https://github.com/searxng/searxng.git "${DIR}/src"
fi

if [ ! -d "${DIR}/.venv" ]; then
  python3 -m venv "${DIR}/.venv"
fi
"${DIR}/.venv/bin/pip" install --upgrade pip >/dev/null
"${DIR}/.venv/bin/pip" install -e "${DIR}/src"

SETTINGS="${DIR}/settings.yml"
if [ ! -f "${SETTINGS}" ]; then
  # The JSON format is off by default upstream; this app reads it, so it must be enabled.
  cat > "${SETTINGS}" <<'YAML'
use_default_settings: true
server:
  bind_address: "127.0.0.1"
  secret_key: "change-me-anything-local"
  limiter: false
search:
  formats:
    - html
    - json
YAML
  echo "Wrote ${SETTINGS} (JSON output enabled - this app needs it)."
fi

cat <<MSG

Done. Start it with:

  SEARXNG_SETTINGS_PATH=${SETTINGS} \\
  ${DIR}/.venv/bin/python -m searx.webapp

It listens on 127.0.0.1:${PORT}. Then set, in config.toml:

  [search]
  base_url = "http://127.0.0.1:${PORT}"

Nothing here is bound off-box, and jarvis refuses a non-loopback search URL.
MSG
