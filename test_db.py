import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# 读取 .env
load_dotenv()
db_url = os.getenv("DATABASE_URL")

print("Using DATABASE_URL:", db_url[:80] + "..." if db_url else "(empty)")

try:
    engine = create_engine(db_url, pool_pre_ping=True)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print("✅ Database connection successful! Result:", result.scalar())
except Exception as e:
    print("❌ Database connection failed:", e)
