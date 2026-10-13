from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


url = settings().database_url.replace("postgres://", "postgresql+psycopg://").replace("postgresql://", "postgresql+psycopg://")
engine = create_engine(url, pool_pre_ping=True, connect_args={"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {})
if url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def pragmas(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")

Session = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    with Session() as db:
        yield db

