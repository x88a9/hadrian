#!/usr/bin/env bash
#
# dev_db.sh — embedded development Postgres for Hadrian³.
#
# Why this exists: pgserver has no cp314 wheel for Python 3.14, so we use the
# portable zonky.io embedded-postgres binaries (PostgreSQL 16.14), which run
# without root.
#
# What it does:
#   - Bootstraps the Postgres binaries into PG_HOME if needed.
#   - Runs initdb into PGDATA if that directory does not exist yet.
#   - Starts the server on port 55432 (TCP on localhost plus a unix socket).
#   - Creates the "hadrian3" role and database if they are missing.
#   - Runs SELECT 1 as a smoke test.
#   - Prints the usable DATABASE_URL (postgresql+psycopg://...) on stdout.
#   - Leaves the server running; calling it again is idempotent.
#   - Exits 0 on success.
set -euo pipefail

# Resolved from this script's location so the paths below stay portable.
REPO_BACKEND="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PG_VERSION="16.14.0"
PG_HOME="${PG_HOME:-$HOME/.local/hadrian3-pg}"
PGDATA="${PGDATA:-$REPO_BACKEND/.devdb}"
PGPORT="${PGPORT:-55432}"
PGHOST="127.0.0.1"
DB_NAME="hadrian3"
DB_USER="hadrian3"
DB_PASS="hadrian3"
# Unix socket directory: a short path, no root required.
SOCKET_DIR="$PGDATA/.sock"

MAVEN_URL="https://repo1.maven.org/maven2/io/zonky/test/postgres/embedded-postgres-binaries-linux-amd64/${PG_VERSION}/embedded-postgres-binaries-linux-amd64-${PG_VERSION}.jar"

log() { echo "[dev_db] $*" >&2; }

# --- 1. Bootstrap the binaries -------------------------------------------------
if [[ ! -x "$PG_HOME/bin/postgres" ]]; then
    log "Postgres binaries missing — downloading zonky embedded-postgres ${PG_VERSION} ..."
    mkdir -p "$PG_HOME"
    tmp_jar="$(mktemp)"
    tmp_txz="$(mktemp)"
    trap 'rm -f "$tmp_jar" "$tmp_txz"' EXIT
    curl -sS -L "$MAVEN_URL" -o "$tmp_jar"
    python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extract('postgres-linux-x86_64.txz', sys.argv[2])" "$tmp_jar" "$(dirname "$tmp_txz")"
    tar -xf "$(dirname "$tmp_txz")/postgres-linux-x86_64.txz" -C "$PG_HOME"
    rm -f "$(dirname "$tmp_txz")/postgres-linux-x86_64.txz"
    log "binaries extracted to $PG_HOME"
fi

INITDB="$PG_HOME/bin/initdb"
PG_CTL="$PG_HOME/bin/pg_ctl"
# The zonky binaries ship server tools only, no psql, so SQL runs through
# psycopg from the backend venv.
PY="${PY:-$REPO_BACKEND/.venv/bin/python}"
export LD_LIBRARY_PATH="$PG_HOME/lib:${LD_LIBRARY_PATH:-}"

# --- 2. initdb, first run only -----------------------------------------
if [[ ! -f "$PGDATA/PG_VERSION" ]]; then
    log "initialising data directory $PGDATA ..."
    mkdir -p "$PGDATA"
    pwfile="$(mktemp)"
    printf '%s' "$DB_PASS" > "$pwfile"
    "$INITDB" -D "$PGDATA" -U "$DB_USER" --auth=trust \
        --pwfile="$pwfile" --encoding=UTF8 >&2
    rm -f "$pwfile"
fi
mkdir -p "$SOCKET_DIR"

# --- 3. Start the server (idempotent) ------------------------------------------
if "$PG_CTL" -D "$PGDATA" status >/dev/null 2>&1; then
    log "server already running."
else
    log "starting Postgres on port $PGPORT ..."
    "$PG_CTL" -D "$PGDATA" -w -l "$PGDATA/server.log" \
        -o "-p $PGPORT -k '$SOCKET_DIR' -c listen_addresses='$PGHOST'" \
        start >&2
fi

# --- 4./5. Create the database + SELECT 1 via psycopg (idempotent) --------------------
DB_NAME="$DB_NAME" DB_USER="$DB_USER" DB_PASS="$DB_PASS" \
PGHOST="$PGHOST" PGPORT="$PGPORT" "$PY" - >&2 <<'PYEOF'
import os
import sys
import time

import psycopg

host = os.environ["PGHOST"]
port = os.environ["PGPORT"]
user = os.environ["DB_USER"]
pw = os.environ["DB_PASS"]
dbname = os.environ["DB_NAME"]

admin_dsn = f"host={host} port={port} user={user} password={pw} dbname=postgres"

# Wait for the server to accept connections.
last = None
for _ in range(60):
    try:
        with psycopg.connect(admin_dsn, connect_timeout=2) as conn:
            break
    except Exception as exc:  # noqa: BLE001
        last = exc
        time.sleep(0.5)
else:
    print(f"[dev_db] server unreachable: {last}", file=sys.stderr)
    sys.exit(1)

# Create the database if missing (CREATE DATABASE needs autocommit).
with psycopg.connect(admin_dsn, autocommit=True) as conn:
    exists = conn.execute(
        "SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)
    ).fetchone()
    if not exists:
        print(f"[dev_db] creating database '{dbname}' ...", file=sys.stderr)
        conn.execute(f'CREATE DATABASE "{dbname}" OWNER "{user}"')

# SELECT 1 against the target database.
target_dsn = f"host={host} port={port} user={user} password={pw} dbname={dbname}"
with psycopg.connect(target_dsn) as conn:
    (val,) = conn.execute("SELECT 1").fetchone()
    if val != 1:
        print("[dev_db] ERROR: SELECT 1 did not return 1.", file=sys.stderr)
        sys.exit(1)
print("[dev_db] SELECT 1 ok.", file=sys.stderr)
PYEOF

# --- 6. DATABASE_URL on stdout ----------------------------------------------
echo "postgresql+psycopg://${DB_USER}:${DB_PASS}@${PGHOST}:${PGPORT}/${DB_NAME}"
