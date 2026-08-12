#!/usr/bin/env python3
"""Additive PostgreSQL migrations for speechAgent (no data loss).

Designed for Azure VM deploys via GitHub Actions:

  - Applies only pending numbered files: database/NNN_*.sql
  - Never runs init.sql (psql \\ir) or DROP SCHEMA
  - Tracks applied files in schema_migrations
  - First run on an existing DB auto-baselines current files (marks applied,
    does not re-execute CREATE TABLE history)
  - Optional compressed pg_dump only when there are pending migrations

Usage (from repo, with backend venv + backend/.env DATABASE_URL):

  python database/migrate.py status
  python database/migrate.py pending-count
  python database/migrate.py apply
  python database/migrate.py dump --dir backups/db --keep 3
  python database/migrate.py baseline   # mark all current files applied (no SQL)

Exit codes:
  0 success
  1 error
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
BACKEND_DIR = REPO_ROOT / "backend"
MIGRATION_RE = re.compile(r"^\d{3}_.+\.sql$", re.IGNORECASE)

TRACKER_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def log(msg: str) -> None:
    """Human-readable progress → stderr so shell capture of stdout stays clean."""
    print(msg, file=sys.stderr)


def _load_database_url() -> str:
    # Prefer already-exported env (CI / systemd). Else load backend/.env.
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if url:
        return url
    env_path = BACKEND_DIR / ".env"
    if env_path.is_file():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_path, override=False)
        except ImportError:
            # Minimal .env reader if python-dotenv missing
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                if key.strip() == "DATABASE_URL" and "DATABASE_URL" not in os.environ:
                    os.environ["DATABASE_URL"] = val.strip().strip('"').strip("'")
        url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise SystemExit(
            "DATABASE_URL is not set. Add it to backend/.env on the VM "
            "(e.g. postgresql://user:pass@localhost:5432/prabhat_DB)."
        )
    return url


def _connect():
    import psycopg2

    url = _load_database_url()
    # SQLAlchemy-style URLs work with psycopg2 if we normalize scheme
    if url.startswith("postgresql+psycopg2://"):
        url = "postgresql://" + url[len("postgresql+psycopg2://") :]
    elif url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    return psycopg2.connect(url)


def list_migration_files() -> List[Path]:
    files = [p for p in ROOT.iterdir() if p.is_file() and MIGRATION_RE.match(p.name)]
    return sorted(files, key=lambda p: p.name)


def ensure_tracker(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(TRACKER_DDL)
    conn.commit()


def applied_filenames(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT filename FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}


def table_exists(conn, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
            LIMIT 1
            """,
            (table,),
        )
        return cur.fetchone() is not None


def pending_files(conn) -> List[Path]:
    applied = applied_filenames(conn)
    return [p for p in list_migration_files() if p.name not in applied]


def mark_applied(conn, filename: str, *, commit: bool = True) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO schema_migrations (filename)
            VALUES (%s)
            ON CONFLICT (filename) DO NOTHING
            """,
            (filename,),
        )
    if commit:
        conn.commit()


def baseline_all(conn, *, reason: str) -> int:
    """Mark every current numbered SQL file as applied without executing SQL."""
    files = list_migration_files()
    for path in files:
        mark_applied(conn, path.name, commit=False)
    conn.commit()
    log(f"[migrate] Baselined {len(files)} file(s) ({reason}). No SQL executed.")
    log(
        "[migrate] Note: if this deploy also introduced brand-new NNN_*.sql files, "
        "remove those filenames from schema_migrations and re-run apply."
    )
    return len(files)


def maybe_auto_baseline(conn) -> bool:
    """
    If tracker is empty but core tables already exist, baseline current files.
    Protects existing Azure VM data from re-running historical CREATE TABLE scripts
    that lack IF NOT EXISTS.
    """
    applied = applied_filenames(conn)
    if applied:
        return False
    if table_exists(conn, "organization") or table_exists(conn, "users"):
        baseline_all(
            conn,
            reason="existing database detected; first migrate run",
        )
        return True
    log("[migrate] Fresh database (no organization/users). Will apply all migrations.")
    return False


def apply_file(conn, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    if sql.startswith("\ufeff"):
        sql = sql.lstrip("\ufeff")
    log(f"[migrate] Applying {path.name} ...")
    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute(
            """
            INSERT INTO schema_migrations (filename)
            VALUES (%s)
            ON CONFLICT (filename) DO NOTHING
            """,
            (path.name,),
        )
    conn.commit()
    log(f"[migrate] OK {path.name}")


def cmd_status(_: argparse.Namespace) -> int:
    conn = _connect()
    try:
        ensure_tracker(conn)
        maybe_auto_baseline(conn)
        pending = pending_files(conn)
        applied = sorted(applied_filenames(conn))
        log(f"[migrate] Applied: {len(applied)}")
        log(f"[migrate] Pending: {len(pending)}")
        for p in pending:
            log(f"  - {p.name}")
        if not pending:
            log("[migrate] Database is up to date.")
        return 0
    finally:
        conn.close()


def cmd_pending_count(_: argparse.Namespace) -> int:
    """Print pending count only on stdout (for shell). Logs go to stderr."""
    conn = _connect()
    try:
        ensure_tracker(conn)
        maybe_auto_baseline(conn)
        # stdout must be a bare integer — used by deploy-vm.yml `[ "$PENDING_COUNT" -gt 0 ]`
        print(len(pending_files(conn)))
        return 0
    finally:
        conn.close()


def cmd_baseline(_: argparse.Namespace) -> int:
    conn = _connect()
    try:
        ensure_tracker(conn)
        baseline_all(conn, reason="manual baseline")
        return 0
    finally:
        conn.close()


def cmd_apply(_: argparse.Namespace) -> int:
    conn = _connect()
    try:
        ensure_tracker(conn)
        maybe_auto_baseline(conn)
        pending = pending_files(conn)
        if not pending:
            log("[migrate] No pending migrations.")
            return 0
        log(f"[migrate] {len(pending)} pending migration(s).")
        for path in pending:
            # One file per transaction: commit on success; rollback file on failure
            try:
                apply_file(conn, path)
            except Exception as ex:
                conn.rollback()
                print(f"[migrate] FAILED on {path.name}: {ex}", file=sys.stderr)
                print(
                    "[migrate] Aborted. Earlier successful files stay applied; "
                    "database data was not dropped.",
                    file=sys.stderr,
                )
                return 1
        log("[migrate] All pending migrations applied successfully.")
        return 0
    finally:
        conn.close()


def _parse_pg_url(url: str) -> dict:
    if url.startswith("postgresql+psycopg2://"):
        url = "postgresql://" + url[len("postgresql+psycopg2://") :]
    elif url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    parsed = urlparse(url)
    if parsed.scheme not in ("postgresql", "postgres"):
        raise ValueError(f"Unsupported DATABASE_URL scheme: {parsed.scheme}")
    db = (parsed.path or "").lstrip("/")
    if not db:
        raise ValueError("DATABASE_URL missing database name")
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": unquote(parsed.username or "postgres"),
        "password": unquote(parsed.password or ""),
        "dbname": db,
    }


def prune_dumps(backup_dir: Path, keep: int) -> None:
    dumps = sorted(
        list(backup_dir.glob("pre_migrate_*.dump"))
        + list(backup_dir.glob("pre_migrate_*.sql.gz")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in dumps[max(0, keep) :]:
        try:
            old.unlink()
            log(f"[migrate] Pruned old dump: {old.name}")
        except OSError as ex:
            log(f"[migrate] Warning: could not delete {old}: {ex}")


def cmd_dump(args: argparse.Namespace) -> int:
    """Compressed schema+data dump (pg_dump -Fc). Does not modify the live DB."""
    backup_dir = Path(args.dir).expanduser()
    if not backup_dir.is_absolute():
        backup_dir = REPO_ROOT / backup_dir
    backup_dir.mkdir(parents=True, exist_ok=True)
    keep = max(1, int(args.keep))

    info = _parse_pg_url(_load_database_url())
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = backup_dir / f"pre_migrate_{ts}.dump"

    env = os.environ.copy()
    if info["password"]:
        env["PGPASSWORD"] = info["password"]

    cmd = [
        "pg_dump",
        "-Fc",
        "--no-owner",
        "--no-acl",
        "-h",
        info["host"],
        "-p",
        info["port"],
        "-U",
        info["user"],
        "-d",
        info["dbname"],
        "-f",
        str(out),
    ]
    log(f"[migrate] Dumping to {out} (schema + data, compressed) ...")
    try:
        subprocess.run(cmd, env=env, check=True)
    except FileNotFoundError:
        print(
            "[migrate] ERROR: pg_dump not found on PATH. "
            "Install postgresql-client on the Azure VM.",
            file=sys.stderr,
        )
        return 1
    except subprocess.CalledProcessError as ex:
        print(f"[migrate] ERROR: pg_dump failed: {ex}", file=sys.stderr)
        return 1

    size_mb = out.stat().st_size / (1024 * 1024)
    log(f"[migrate] Dump OK ({size_mb:.2f} MiB): {out}")
    prune_dumps(backup_dir, keep)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safe additive DB migrations for speechAgent (no DROP SCHEMA)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show applied / pending migrations")
    sub.add_parser("pending-count", help="Print pending count (for shell)")
    sub.add_parser("apply", help="Apply pending migrations only")
    sub.add_parser(
        "baseline",
        help="Mark all current SQL files applied without running them",
    )

    dump_p = sub.add_parser(
        "dump",
        help="pg_dump -Fc backup (schema+data); prune old dumps",
    )
    dump_p.add_argument(
        "--dir",
        default="backups/db",
        help="Backup directory (default: backups/db under repo)",
    )
    dump_p.add_argument(
        "--keep",
        type=int,
        default=3,
        help="Keep newest N dumps (default: 3)",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "pending-count":
        return cmd_pending_count(args)
    if args.command == "apply":
        return cmd_apply(args)
    if args.command == "baseline":
        return cmd_baseline(args)
    if args.command == "dump":
        return cmd_dump(args)
    parser.error(f"Unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
