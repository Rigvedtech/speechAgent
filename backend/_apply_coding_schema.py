"""Apply coding-round SQL migrations. Run: python _apply_coding_schema.py"""

from pathlib import Path

from sqlalchemy import text

from db.session import get_engine

ROOT = Path(__file__).resolve().parents[1] / "database"
FILES = [
    "025_coding_round.sql",
    "028_coding_entry_function.sql",
    "026_coding_tasks_seed.sql",
    "027_coding_candidate_access.sql",
    "029_coding_domains.sql",
    "030_coding_languages_expand.sql",
    "031_coding_multi_task_times.sql",
]


def main() -> None:
    eng = get_engine()
    raw = eng.raw_connection()
    try:
        cur = raw.cursor()
        for name in FILES:
            sql = (ROOT / name).read_text(encoding="utf-8")
            print(f"Applying {name} ...")
            cur.execute(sql)
            print(f"OK {name}")
        raw.commit()
    finally:
        raw.close()

    with eng.connect() as conn:
        rows = conn.execute(
            text("SELECT slug, title, difficulty FROM coding_tasks ORDER BY slug")
        ).mappings().all()
        print("tasks:", [dict(r) for r in rows])
        tables = conn.execute(
            text(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                    'coding_tasks',
                    'interview_coding_configs',
                    'coding_submissions'
                  )
                ORDER BY table_name
                """
            )
        ).fetchall()
        print("tables:", [t[0] for t in tables])


if __name__ == "__main__":
    main()
