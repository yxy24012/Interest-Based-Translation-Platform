This project has been patched to use external PostgreSQL (Supabase/Railway).

Changes:
- app.py: reads DATABASE_URL, converts postgres:// to postgresql+psycopg2://, enforces sslmode=require, and makes ALTER TABLE boolean defaults dialect-aware.
- requirements.txt: added psycopg2-binary and python-dotenv.
- init_db.py: safe, idempotent DB initializer for Postgres.
Usage:
1) Set DATABASE_URL in your environment (Render Environment or local .env).
2) Deploy; then run `python init_db.py` once to create tables.
