# db.py

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, Session
import os, datetime

Base = declarative_base()

def init_db(db_url=None):
    url = db_url or os.getenv("MYSQL_URL")
    if not url:
        raise RuntimeError("MYSQL_URL is not set!")
    engine = create_engine(url, echo=False, future=True)
    # import your model classes here so SQLAlchemy picks them up:
    from .models import Lead   # wherever your Lead model lives
    Base.metadata.create_all(engine)
    # store engine on module for save_lead to use
    globals()["_engine"] = engine

def get_session():
    return Session(globals()["_engine"])

def save_lead(name, email, phone, notes=""):
    with get_session() as sess:
        sess.add(Lead(name=name, email=email, phone=phone, notes=notes))
        sess.commit()
