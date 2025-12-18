"""
Database models for Video Bot v4.0
Using SQLAlchemy with PostgreSQL
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, BigInteger, Boolean, Float, Text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


class VideoCache(Base):
    """Cached video metadata and file location"""
    __tablename__ = 'video_cache'

    id = Column(Integer, primary_key=True)
    url_hash = Column(String(64), unique=True, index=True, nullable=False)
    original_url = Column(Text, nullable=False)
    platform = Column(String(32), nullable=False, index=True)
    quality = Column(String(16), nullable=False)
    format = Column(String(16), nullable=False, default='video')

    # File info
    file_key = Column(String(256), nullable=True)  # MinIO object key
    file_size = Column(BigInteger, nullable=True)
    file_path = Column(String(512), nullable=True)  # Local fallback

    # Metadata
    title = Column(String(512), nullable=True)
    duration = Column(Integer, nullable=True)
    thumbnail = Column(Text, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)

    # Stats
    access_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_accessed = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_cache_platform_created', 'platform', 'created_at'),
    )


class Download(Base):
    """Download task tracking"""
    __tablename__ = 'downloads'

    id = Column(String(36), primary_key=True)  # UUID
    url = Column(Text, nullable=False)
    platform = Column(String(32), nullable=False)
    quality = Column(String(16), nullable=False)
    format = Column(String(16), nullable=False, default='video')

    # User info
    user_id = Column(BigInteger, nullable=False, index=True)
    chat_id = Column(BigInteger, nullable=False)
    message_id = Column(Integer, nullable=True)

    # Status
    status = Column(String(32), default='pending', index=True)  # pending, downloading, completed, error
    progress = Column(Float, default=0.0)
    error = Column(Text, nullable=True)

    # Result
    file_key = Column(String(256), nullable=True)
    file_size = Column(BigInteger, nullable=True)
    title = Column(String(512), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index('idx_downloads_status_created', 'status', 'created_at'),
    )


class UserStats(Base):
    """User statistics and rate limiting"""
    __tablename__ = 'user_stats'

    user_id = Column(BigInteger, primary_key=True)
    username = Column(String(64), nullable=True)
    first_name = Column(String(128), nullable=True)

    # Stats
    total_downloads = Column(Integer, default=0)
    total_bytes = Column(BigInteger, default=0)
    last_request = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GroupStats(Base):
    """Group statistics and rate limiting"""
    __tablename__ = 'group_stats'

    chat_id = Column(BigInteger, primary_key=True)
    title = Column(String(256), nullable=True)

    # Stats
    total_downloads = Column(Integer, default=0)
    last_request = Column(DateTime, nullable=True)

    # Settings
    is_enabled = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)


async def init_db(database_url: str):
    """Initialize database and create tables"""
    # Convert to async URL
    if database_url.startswith('postgresql://'):
        database_url = database_url.replace('postgresql://', 'postgresql+asyncpg://')

    engine = create_async_engine(database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    return engine


def get_async_session(engine):
    """Get async session factory"""
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
