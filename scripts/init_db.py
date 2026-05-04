"""One-shot DB initializer. Safe to run multiple times."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from execution.db.sqlite import connect, init_db

conn = connect()
init_db(conn)

tables = [row[0] for row in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()]

print("DB ready.")
print("Tables:", tables)
