# db.py
import os
import datetime
from sqlalchemy import create_engine, Column, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# Pull in your Hostinger MySQL URL from env (set this in Railway)
# e.g. mysql+pymysql://user:pass@host:port/dbname
DB_URL = os.getenv("MYSQL_URL")
if not DB_URL:
    raise RuntimeError("MYSQL_URL is not set!")

# create the engine & session factory
engine = create_engine(DB_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()

class Lead(Base):
    __tablename__ = "leads"
    phone      = Column(String(32), primary_key=True, index=True)
    name       = Column(String(128), nullable=False)
    email      = Column(String(256), nullable=False)
    notes      = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

def init_db():
    # This will create the table if it doesn’t exist
    Base.metadata.create_all(bind=engine)

def save_lead(name: str, email: str, phone: str, notes: str = ""):
    db = SessionLocal()
    try:
        db_lead = Lead(name=name, email=email, phone=phone, notes=notes)
        db.add(db_lead)
        db.commit()
    finally:
        db.close()
