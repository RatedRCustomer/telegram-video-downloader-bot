"""Initial migration - create all tables

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create video_cache table
    op.create_table(
        'video_cache',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('url', sa.String(length=2048), nullable=False),
        sa.Column('url_hash', sa.String(length=64), nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=True),
        sa.Column('duration', sa.Integer(), nullable=True),
        sa.Column('thumbnail', sa.String(length=1024), nullable=True),
        sa.Column('uploader', sa.String(length=255), nullable=True),
        sa.Column('view_count', sa.BigInteger(), nullable=True),
        sa.Column('formats', postgresql.JSONB(), nullable=True),
        sa.Column('file_path', sa.String(length=1024), nullable=True),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        sa.Column('telegram_file_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_video_cache_url_hash', 'video_cache', ['url_hash'], unique=True)
    op.create_index('ix_video_cache_platform', 'video_cache', ['platform'], unique=False)
    op.create_index('ix_video_cache_expires_at', 'video_cache', ['expires_at'], unique=False)

    # Create downloads table
    op.create_table(
        'downloads',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=True),
        sa.Column('url', sa.String(length=2048), nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=False),
        sa.Column('quality', sa.String(length=20), nullable=True),
        sa.Column('format_type', sa.String(length=20), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='pending', nullable=True),
        sa.Column('progress', sa.Integer(), server_default='0', nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('file_path', sa.String(length=1024), nullable=True),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        sa.Column('telegram_file_id', sa.String(length=255), nullable=True),
        sa.Column('celery_task_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_downloads_user_id', 'downloads', ['user_id'], unique=False)
    op.create_index('ix_downloads_status', 'downloads', ['status'], unique=False)
    op.create_index('ix_downloads_created_at', 'downloads', ['created_at'], unique=False)

    # Create user_stats table
    op.create_table(
        'user_stats',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.String(length=255), nullable=True),
        sa.Column('first_name', sa.String(length=255), nullable=True),
        sa.Column('language_code', sa.String(length=10), nullable=True),
        sa.Column('total_downloads', sa.Integer(), server_default='0', nullable=True),
        sa.Column('total_size_bytes', sa.BigInteger(), server_default='0', nullable=True),
        sa.Column('youtube_downloads', sa.Integer(), server_default='0', nullable=True),
        sa.Column('instagram_downloads', sa.Integer(), server_default='0', nullable=True),
        sa.Column('tiktok_downloads', sa.Integer(), server_default='0', nullable=True),
        sa.Column('twitter_downloads', sa.Integer(), server_default='0', nullable=True),
        sa.Column('other_downloads', sa.Integer(), server_default='0', nullable=True),
        sa.Column('favorite_quality', sa.String(length=20), nullable=True),
        sa.Column('first_seen', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('last_seen', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('is_premium', sa.Boolean(), server_default='false', nullable=True),
        sa.Column('is_blocked', sa.Boolean(), server_default='false', nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_user_stats_user_id', 'user_stats', ['user_id'], unique=True)

    # Create group_stats table
    op.create_table(
        'group_stats',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=True),
        sa.Column('chat_type', sa.String(length=20), nullable=True),
        sa.Column('total_downloads', sa.Integer(), server_default='0', nullable=True),
        sa.Column('unique_users', sa.Integer(), server_default='0', nullable=True),
        sa.Column('added_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('last_activity', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_group_stats_chat_id', 'group_stats', ['chat_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_group_stats_chat_id', table_name='group_stats')
    op.drop_table('group_stats')
    op.drop_index('ix_user_stats_user_id', table_name='user_stats')
    op.drop_table('user_stats')
    op.drop_index('ix_downloads_created_at', table_name='downloads')
    op.drop_index('ix_downloads_status', table_name='downloads')
    op.drop_index('ix_downloads_user_id', table_name='downloads')
    op.drop_table('downloads')
    op.drop_index('ix_video_cache_expires_at', table_name='video_cache')
    op.drop_index('ix_video_cache_platform', table_name='video_cache')
    op.drop_index('ix_video_cache_url_hash', table_name='video_cache')
    op.drop_table('video_cache')
