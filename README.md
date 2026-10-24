<div align="center">

# 🛡️ LLM Firewalls: An Introduction

### Inspect model-generated SQL before it reaches your database

A small, local proof of concept built with **Ollama**, **Python**, and
**PostgreSQL**.

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL 17](https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Ollama](https://img.shields.io/badge/Ollama-local_LLM-111111)](https://ollama.com/)

[Overview](#overview) · [Demo](#video-walkthrough) · [Quick start](#quick-start) · [Architecture](#how-it-works) · [Security notes](#security-notes)

</div>

> [!IMPORTANT]
> This repository is an educational demonstration, not a production-ready
> security control. Run the unprotected mode only against the included local,
> fictional data.

## Overview

LLMs can generate useful database queries—but executing that SQL without an
application-controlled safety boundary is risky. This project demonstrates a
simple boundary that inspects every model-generated query before PostgreSQL can
execute it.

| Mode | SQL path | Behavior |
| --- | --- | --- |
| 🟢 **Protected** (default) | Ollama → firewall → PostgreSQL | Allows read-oriented queries and blocks modifying or administrative SQL |
| 🟠 **Unprotected** (demo only) | Ollama → PostgreSQL | Executes model-generated SQL directly to make the risk visible |

The application—not the model—selects the execution mode. The model cannot
bypass the firewall through a tool argument.

## Video walkthrough

<div align="center">

[![Watch the LLM Firewalls introduction video](https://img.youtube.com/vi/oZbMvaFHqyw/maxresdefault.jpg)](https://youtu.be/oZbMvaFHqyw)

*Click the image to watch the introduction.*

</div>

## Quick start

### Prerequisites

Before you begin, make sure you have:

- [Python 3.10+](https://www.python.org/downloads/)
- [Docker](https://docs.docker.com/get-docker/) with Docker Compose v2
- [Ollama](https://ollama.com/)
- [uv](https://docs.astral.sh/uv/) (optional; `run.sh` falls back to `python3 -m venv` and pip)

Run all commands from the repository root.

### One command

```bash
./run.sh
```

Then open <http://127.0.0.1:8001>. The script does the setup below for you, and
every step is safe to repeat:

1. Creates `configurations/.env` from `.env.example` with a random local
   database password, if the file does not exist.
2. Starts PostgreSQL in Docker. If port 5432 is already taken by another
   program, it picks the next free port and saves it as `POSTGRES_PORT` in
   `configurations/.env`, so `python main.py` uses the same port.
3. Creates `.venv` and installs `requirments.txt`.
4. Starts `ollama serve` if Ollama is not running (and stops it again on exit),
   and pulls the model the first time.
5. Launches the web UI on `127.0.0.1:8001`. It uses 8001 rather than 8000 so it
   can run next to the [local LLM pentesting lab](https://github.com/samliumay/local_llm_pentesting_lab) UI.

| Command | What it does |
| --- | --- |
| `./run.sh` | Set up everything and start the web UI |
| `./run.sh --cli` | Same setup, then start the terminal chat (`main.py`) |
| `./run.sh --cli -- --disable-firewall` | Terminal chat in unprotected mode |
| `./run.sh --model llama3.1:8b` | Use another Ollama model for this run |
| `./run.sh --port 8080` | Serve the web UI on another port (a busy port is skipped automatically) |
| `./run.sh --stop` | Stop the database container (data is kept) |

The default model is `qwen3.6:35b`, a download of over 20 GB the first time. For a
quicker start on smaller machines, use `--model llama3.1:8b`, or set
`OLLAMA_MODEL=llama3.1:8b` in `configurations/.env` to make it the default.

> [!NOTE]
> PostgreSQL only applies `POSTGRES_USER`, `POSTGRES_DB`, and `POSTGRES_PASSWORD`
> when its data volume is first created. If you change them later, reset the demo
> data with `docker compose -f configurations/docker-compose.yml down -v && ./run.sh`.

The numbered steps below do the same thing by hand.

### 1. Create the Python environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirments.txt
```

If the virtual environment already exists, activate it and install any missing
dependencies.

### 2. Configure PostgreSQL

Create a local environment file:

```bash
cp configurations/.env.example configurations/.env
```

Open `configurations/.env` and replace the example password with a local
password of your choice. This file is ignored by Git.

Start PostgreSQL and check that it is healthy:

```bash
docker compose -f configurations/docker-compose.yml up -d
docker compose -f configurations/docker-compose.yml ps
```

The first startup creates a `customers` table and fills it with fictional sample
data from `configurations/postgres/init/`. PostgreSQL listens on
`127.0.0.1:5432`; to use another port, set `POSTGRES_PORT` in
`configurations/.env` (Compose and the application both read it).

<details>
<summary><strong>Inspect the sample data directly</strong></summary>

```bash
docker compose -f configurations/docker-compose.yml exec database \
  psql -U firewall_user -d firewall_bank
```

Then run:

```sql
SELECT * FROM customers;
```

Type `\q` to leave the PostgreSQL shell.

</details>

### 3. Start Ollama

Download the default tool-capable model:

```bash
ollama pull qwen3.6
```

If Ollama is not already running as a background service, start it in a separate
terminal:

```bash
ollama serve
```

The application connects to Ollama at `http://localhost:11434/api/chat`.

### 4. Run the protected demo

The firewall is enabled by default:

```bash
python main.py
```

To use another locally installed, tool-capable model:

```bash
python main.py --model qwen3
```

Try asking the assistant to read the customer data, then ask it to modify a
record. Queries beginning with `SELECT`, `WITH`, `SHOW`, or `EXPLAIN` can pass;
keywords such as `INSERT`, `UPDATE`, `DELETE`, and `DROP` are blocked.

### 5. Compare with unprotected mode

```bash
python main.py --disable-firewall
```

This deliberately allows model-generated SQL to modify the demonstration
database. Use it only with the included local data.

Type `exit` or `quit` in either mode to end the conversation.

### Web UI

A [Gradio](https://www.gradio.app/) interface wraps the same Ollama integration and firewall. The easiest
way to start it is [`./run.sh`](#one-command), which also starts PostgreSQL and
Ollama. To launch only the web server yourself, with PostgreSQL and Ollama
already running:

```bash
python web.py                       # http://127.0.0.1:8000
python web.py --port 8080 --model qwen3
```

The server listens on `127.0.0.1` only. In the page you can:

- chat with the banking assistant, and see each SQL query the model generated
  with its firewall verdict (`ALLOWED`, `BLOCKED`, or `NOT INSPECTED`), the
  block reason, and the returned rows or database error;
- switch between protected and unprotected mode, or pick another installed
  model (either change starts a new conversation);
- test a SQL string against the firewall rules alone, without the model or the
  database.

If Ollama or PostgreSQL is unavailable, the page shows the error and any
firewall verdicts reached before the failure.

### 6. Stop the database

```bash
docker compose -f configurations/docker-compose.yml down
```

PostgreSQL data remains in a Docker volume. The initialization scripts run only
when that volume is first created.

## How it works

```mermaid
flowchart LR
    U[User prompt] --> O[Ollama]
    O -->|Tool call with SQL| M{Execution mode}
    M -->|Protected| F[SQL firewall]
    F -->|Allowed read| P[(PostgreSQL)]
    F -->|Unsafe query| B[Blocked]
    M -->|Unprotected demo| P
    P --> R[Tool result]
    R --> O
    O --> A[Final answer]
```

1. `main.py` selects protected or unprotected mode and starts the interactive
   chat.
2. `llm_integrations/ollama_based_integration.py` sends the conversation and
   the database tool definition to Ollama.
3. When Ollama calls `execute_database_query`, the generated SQL is passed to
   `llm_integrations/database_layer.py`.
4. In protected mode, `firewall/firewall_class.py` validates the SQL before the
   database layer can execute it.
5. The database result—or the firewall error—is returned to Ollama as a tool
   message so it can produce a final answer.

## Project structure

```text
.
├── configurations/
│   ├── docker-compose.yml       # Local PostgreSQL service
│   └── postgres/init/           # Schema and fictional sample data
├── firewall/
│   └── firewall_class.py        # SQL inspection rules
├── llm_integrations/
│   ├── database_layer.py        # Protected and direct execution paths
│   └── ollama_based_integration.py
├── webui/                       # Gradio app for the web UI
├── main.py                      # Command-line entry point
├── run.sh                       # One-command setup and launcher
├── web.py                       # Web UI entry point
└── requirments.txt              # Python dependencies
```

## Security notes

- The firewall is intentionally basic: it uses allow-list and deny-list regular
  expressions, not a full SQL parser.
- Protected mode allows statements beginning with `SELECT`, `WITH`, `SHOW`, or
  `EXPLAIN` after rejecting known modifying and administrative keywords.
- Unprotected mode exists only to demonstrate the danger of trusting generated
  SQL.
- The database binds to `127.0.0.1`, and the included records are fictional.

> [!CAUTION]
> Do not treat this proof of concept as a replacement for least-privilege
> database roles, read-only transactions, query parsing, auditing, or other
> production security controls.
