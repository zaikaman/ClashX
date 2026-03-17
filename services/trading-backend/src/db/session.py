from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from src.core.settings import get_settings

settings = get_settings()
Base = declarative_base()

if settings.database_url:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
else:
    engine = None

    def SessionLocal():  # type: ignore[no-redef]
        return None


def get_db():
    if engine is None:
        yield None
        return
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
