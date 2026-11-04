"""A real, empty Postgres for the demo and the tests. It lives in a temporary folder,
nothing touches a real database, and it is deleted at the end."""
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pgserver
import psycopg2

ROOT = Path(__file__).resolve().parent.parent


@contextmanager
def throwaway_postgres():
    folder = tempfile.mkdtemp(prefix="demo_pg_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    try:
        dsn = server.get_uri()
        conn = psycopg2.connect(dsn)
        with conn.cursor() as cur:
            cur.execute((ROOT / "ops" / "local_supabase_standin.sql").read_text(encoding="utf-8"))
            for f in sorted((ROOT / "sql").glob("*.sql")):
                cur.execute(f.read_text(encoding="utf-8"))
        conn.commit()
        conn.close()
        yield dsn
    finally:
        server.cleanup()
        shutil.rmtree(folder, ignore_errors=True)
