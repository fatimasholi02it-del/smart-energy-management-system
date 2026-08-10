from sqlalchemy import create_engine, text
from config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=300,
)

with engine.connect() as conn:
    result = conn.execute(text("SELECT 1"))
    print("DB OK:", result.scalar())