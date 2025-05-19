# db.py

import os
import datetime
from sqlalchemy import create_engine, Column, String, Text, DateTime
from sqlalchemy.orm import declarative_base, Session

# ── CONFIG ─────────────────────────────────────────────────────────────────
DB_URL = os.getenv("MYSQL_URL")
if not DB_URL:
    raise RuntimeError("MYSQL_URL is not set!")

# ── SQLAlchemy SETUP ─────────────────────────────────────────────────────────
Base   = declarative_base()
_engine = create_engine(DB_URL, echo=False, future=True)

class Lead(Base):
    __tablename__ = "leads"
    phone      = Column(String(32), primary_key=True)
    name       = Column(String(128), nullable=False)
    email      = Column(String(256), nullable=False)
    notes      = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

def init_db():
    """Create the leads table if it doesn't exist."""
    Base.metadata.create_all(_engine)

def save_lead(name: str, email: str, phone: str, notes: str = ""):
    """Add a new Lead row to the database."""
    with Session(_engine) as sess:
        sess.add(Lead(name=name, email=email, phone=phone, notes=notes))
        sess.commit()
