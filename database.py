import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Expects DATABASE_URL from environment (e.g., docker-compose)
# Default fallback to a local PostgreSQL instance for standalone testing
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://sahayak:sahayak_pass@db:5432/sahayakdb"
)

# Wait a moment for DB in docker-compose, but we rely on depends_on in compose.
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency for FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
