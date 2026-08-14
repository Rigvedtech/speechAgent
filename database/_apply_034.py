from pathlib import Path
import os
import sys

sys.path.insert(0, "backend")
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("backend/.env")
engine = create_engine(os.environ["DATABASE_URL"])
sql = Path("database/034_access_requests.sql").read_text(encoding="utf-8")
with engine.begin() as conn:
    conn.execute(text(sql))
    conn.execute(text("DELETE FROM schema_migrations WHERE filename = :f"), {"f": "034_access_requests.sql"})
    conn.execute(text("INSERT INTO schema_migrations (filename) VALUES (:f)"), {"f": "034_access_requests.sql"})
print("applied 034_access_requests.sql")
