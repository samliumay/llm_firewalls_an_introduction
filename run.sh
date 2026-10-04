#!/usr/bin/env bash
# One-command launcher for the LLM firewall demonstration.
#
#   ./run.sh                 set everything up and start the web UI
#   ./run.sh --cli [-- ARGS] same setup, then start the terminal chat (main.py);
#                            e.g. ./run.sh --cli -- --disable-firewall
#   ./run.sh --model NAME    use a different Ollama model for this run
#   ./run.sh --port N        serve the web UI on port N (default: 8001)
#   ./run.sh --stop          stop the demo database container
#
# The script creates configurations/.env, starts PostgreSQL in Docker on a free
# port, installs the Python packages, makes sure Ollama is running with the
# model, and then launches the app. Every step is safe to repeat.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$PROJECT_DIR/configurations"
ENV_FILE="$CONFIG_DIR/.env"
COMPOSE=(docker compose -f "$CONFIG_DIR/docker-compose.yml")
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
OLLAMA_API="http://127.0.0.1:11434"

MODE="web"
MODEL_OVERRIDE=""
WEB_PORT="8001"
CLI_ARGS=()

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# Read KEY from configurations/.env, without quotes.
env_get() {
    grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- | tr -d '"'"'" || true
}

# Set KEY=VALUE in configurations/.env, replacing an existing line.
env_set() {
    if grep -qE "^$1=" "$ENV_FILE"; then
        sed -i.bak -E "s|^$1=.*|$1=$2|" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
    else
        printf '\n%s=%s\n' "$1" "$2" >> "$ENV_FILE"
    fi
}

port_in_use() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

first_free_port() {
    local port=$1
    while port_in_use "$port"; do port=$((port + 1)); done
    echo "$port"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --cli) MODE="cli" ;;
        --stop) MODE="stop" ;;
        --model) MODEL_OVERRIDE="${2:?--model needs a name}"; shift ;;
        --port) WEB_PORT="${2:?--port needs a number}"; shift ;;
        --) shift; CLI_ARGS=("$@"); break ;;
        -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) die "unknown option: $1 (see ./run.sh --help)" ;;
    esac
    shift
done

command -v docker >/dev/null || die "Docker is required: https://docs.docker.com/get-docker/"
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required (the 'docker compose' command)."
docker info >/dev/null 2>&1 || die "The Docker daemon is not running (or this user cannot access it)."

if [[ "$MODE" == "stop" ]]; then
    info "Stopping the demo database (data is kept in its Docker volume)"
    "${COMPOSE[@]}" stop database
    exit 0
fi

# 1. Configuration --------------------------------------------------------
if [[ ! -f "$ENV_FILE" ]]; then
    info "Creating configurations/.env with a random local database password"
    cp "$CONFIG_DIR/.env.example" "$ENV_FILE"
    env_set POSTGRES_PASSWORD "$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)"
    if docker volume inspect llm-firewall-bank_bank_postgres_data >/dev/null 2>&1; then
        warn "An old database volume exists and keeps its old password. If login fails, reset it with:"
        warn "  docker compose -f configurations/docker-compose.yml down -v"
    fi
fi

# 2. PostgreSQL -----------------------------------------------------------
# Reuse the port of an already running demo container; otherwise keep the
# configured port, or move to the next free one if something else holds it.
DB_PORT=""
if [[ -n "$("${COMPOSE[@]}" ps -q --status running database 2>/dev/null)" ]]; then
    DB_PORT="$("${COMPOSE[@]}" port database 5432 2>/dev/null | awk -F: 'NR==1{print $NF}')"
fi
if [[ -z "$DB_PORT" ]]; then
    DB_PORT="$(env_get POSTGRES_PORT)"
    DB_PORT="${DB_PORT:-5432}"
    if port_in_use "$DB_PORT"; then
        NEW_PORT="$(first_free_port $((DB_PORT + 1)))"
        warn "Port $DB_PORT is used by another program; the demo database will use $NEW_PORT."
        DB_PORT="$NEW_PORT"
    fi
fi
if [[ "$(env_get POSTGRES_PORT)" != "$DB_PORT" ]]; then
    env_set POSTGRES_PORT "$DB_PORT"
fi
export POSTGRES_PORT="$DB_PORT"

info "Starting PostgreSQL on 127.0.0.1:$DB_PORT"
"${COMPOSE[@]}" up -d database >/dev/null

DB_USER="$(env_get POSTGRES_USER)"
DB_NAME="$(env_get POSTGRES_DB)"
# TCP check: the temporary server used while seeding listens on a socket only,
# so this succeeds once the seed scripts have finished.
for attempt in $(seq 1 60); do
    if "${COMPOSE[@]}" exec -T database pg_isready -q -h 127.0.0.1 -U "$DB_USER" -d "$DB_NAME" 2>/dev/null; then
        break
    fi
    [[ $attempt -eq 60 ]] && die "PostgreSQL did not become ready. Check: docker compose -f configurations/docker-compose.yml logs database"
    sleep 1
done

# The init scripts only run on an empty volume, so an older volume keeps the
# credentials it was created with. Catch that here instead of at login time.
if ! "${COMPOSE[@]}" exec -T database psql -q -U "$DB_USER" -d "$DB_NAME" -c 'select 1' >/dev/null 2>&1; then
    warn "The database volume was created with a different POSTGRES_USER/POSTGRES_DB than configurations/.env."
    warn "Either put the original values back in configurations/.env, or reset the volume (deletes its data):"
    die "  docker compose -f configurations/docker-compose.yml down -v && ./run.sh"
fi

# 3. Python environment ---------------------------------------------------
if command -v uv >/dev/null; then
    [[ -x "$VENV_PYTHON" ]] || { info "Creating .venv with uv"; uv venv --quiet "$PROJECT_DIR/.venv"; }
    info "Installing Python packages"
    uv pip install --quiet --python "$VENV_PYTHON" -r "$PROJECT_DIR/requirments.txt"
else
    command -v python3 >/dev/null || die "Python 3.11+ (or uv) is required."
    [[ -x "$VENV_PYTHON" ]] || { info "Creating .venv"; python3 -m venv "$PROJECT_DIR/.venv"; }
    info "Installing Python packages"
    "$VENV_PYTHON" -m pip install --quiet -r "$PROJECT_DIR/requirments.txt"
fi

# 4. Ollama -----------------------------------------------------------------
OLLAMA_PID=""
cleanup() { [[ -n "$OLLAMA_PID" ]] && kill "$OLLAMA_PID" 2>/dev/null || true; }
trap cleanup EXIT

if ! curl -fsS "$OLLAMA_API/api/version" >/dev/null 2>&1; then
    command -v ollama >/dev/null || die "Ollama is required: https://ollama.com/download"
    info "Starting Ollama in the background (log: .ollama-serve.log)"
    ollama serve >"$PROJECT_DIR/.ollama-serve.log" 2>&1 &
    OLLAMA_PID=$!
    for attempt in $(seq 1 30); do
        curl -fsS "$OLLAMA_API/api/version" >/dev/null 2>&1 && break
        [[ $attempt -eq 30 ]] && die "Ollama did not start. See .ollama-serve.log"
        sleep 1
    done
fi

MODEL="${MODEL_OVERRIDE:-$(env_get OLLAMA_MODEL)}"
MODEL="${MODEL:-qwen3.6:35b}"
if ! curl -fsS "$OLLAMA_API/api/show" -d "{\"model\":\"$MODEL\"}" >/dev/null 2>&1; then
    command -v ollama >/dev/null || die "Model '$MODEL' is missing and the ollama CLI is not installed to pull it."
    info "Downloading Ollama model '$MODEL' (first run only)"
    ollama pull "$MODEL"
fi

# 5. Launch -------------------------------------------------------------------
cd "$PROJECT_DIR"
info "Ready: database on port $DB_PORT, model $MODEL"
if [[ "$MODE" == "cli" ]]; then
    "$VENV_PYTHON" main.py --model "$MODEL" ${CLI_ARGS[@]+"${CLI_ARGS[@]}"}
else
    if port_in_use "$WEB_PORT"; then
        NEW_PORT="$(first_free_port $((WEB_PORT + 1)))"
        warn "Port $WEB_PORT is busy; using $NEW_PORT for the web UI."
        WEB_PORT="$NEW_PORT"
    fi
    info "Open http://127.0.0.1:$WEB_PORT  (Ctrl+C to stop; './run.sh --stop' stops the database)"
    "$VENV_PYTHON" web.py --port "$WEB_PORT" --model "$MODEL"
fi
