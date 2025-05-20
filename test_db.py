# test_db.py
import os
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# Retrieve the database URL from the environment
# Ensure you set MYSQL_URL in your Railway variables or .env:
# mysql+pymysql://<USER>:<PASSWORD>@<HOST>:3306/<DATABASE>
DB_URL = os.getenv("MYSQL_URL")
if not DB_URL:
    raise RuntimeError("MYSQL_URL is not set. Please configure it as an environment variable.")

# Create SQLAlchemy engine
engine = create_engine(DB_URL, echo=True, future=True)

try:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print("✔ SELECT 1 ->", result.scalar())
except SQLAlchemyError as e:
    print("❌ Database connection failed:")
    print(e)
