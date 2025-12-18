"""
MinIO storage client for video files
"""
import os
import uuid
from pathlib import Path
from typing import Optional, BinaryIO
from datetime import timedelta

from minio import Minio
from minio.error import S3Error


class StorageClient:
    """MinIO storage client"""

    def __init__(
        self,
        endpoint: str = None,
        access_key: str = None,
        secret_key: str = None,
        bucket: str = None,
        secure: bool = False
    ):
        self.endpoint = endpoint or os.getenv('MINIO_ENDPOINT', 'localhost:9000')
        self.access_key = access_key or os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
        self.secret_key = secret_key or os.getenv('MINIO_SECRET_KEY', 'minioadmin123')
        self.bucket = bucket or os.getenv('MINIO_BUCKET', 'videos')
        self.secure = secure
        self.client: Optional[Minio] = None

    def connect(self):
        """Connect to MinIO"""
        self.client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure
        )

        # Ensure bucket exists
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def generate_key(self, platform: str, ext: str = 'mp4') -> str:
        """Generate unique object key"""
        return f"{platform}/{uuid.uuid4().hex}.{ext}"

    def upload_file(self, file_path: str, object_key: str = None, platform: str = 'unknown') -> str:
        """
        Upload file to MinIO
        Returns: object key
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = path.suffix.lstrip('.') or 'mp4'
        object_key = object_key or self.generate_key(platform, ext)

        # Determine content type
        content_type = 'video/mp4'
        if ext == 'mp3':
            content_type = 'audio/mpeg'
        elif ext == 'webm':
            content_type = 'video/webm'

        self.client.fput_object(
            self.bucket,
            object_key,
            file_path,
            content_type=content_type
        )

        return object_key

    def upload_stream(self, data: BinaryIO, object_key: str, length: int, content_type: str = 'video/mp4') -> str:
        """Upload from stream"""
        self.client.put_object(
            self.bucket,
            object_key,
            data,
            length=length,
            content_type=content_type
        )
        return object_key

    def download_file(self, object_key: str, destination: str) -> str:
        """
        Download file from MinIO
        Returns: local file path
        """
        self.client.fget_object(self.bucket, object_key, destination)
        return destination

    def get_presigned_url(self, object_key: str, expires: int = 3600) -> str:
        """Get presigned URL for direct download"""
        return self.client.presigned_get_object(
            self.bucket,
            object_key,
            expires=timedelta(seconds=expires)
        )

    def delete_file(self, object_key: str):
        """Delete file from MinIO"""
        try:
            self.client.remove_object(self.bucket, object_key)
        except S3Error:
            pass

    def file_exists(self, object_key: str) -> bool:
        """Check if file exists"""
        try:
            self.client.stat_object(self.bucket, object_key)
            return True
        except S3Error:
            return False

    def get_file_info(self, object_key: str) -> Optional[dict]:
        """Get file metadata"""
        try:
            stat = self.client.stat_object(self.bucket, object_key)
            return {
                'size': stat.size,
                'content_type': stat.content_type,
                'last_modified': stat.last_modified,
            }
        except S3Error:
            return None

    def get_file_stream(self, object_key: str):
        """Get file as stream"""
        response = self.client.get_object(self.bucket, object_key)
        return response

    def list_files(self, prefix: str = '', limit: int = 100) -> list:
        """List files in bucket"""
        objects = self.client.list_objects(self.bucket, prefix=prefix)
        result = []
        for obj in objects:
            if len(result) >= limit:
                break
            result.append({
                'key': obj.object_name,
                'size': obj.size,
                'last_modified': obj.last_modified,
            })
        return result

    def get_bucket_stats(self) -> dict:
        """Get bucket statistics"""
        total_size = 0
        total_count = 0

        for obj in self.client.list_objects(self.bucket, recursive=True):
            total_size += obj.size
            total_count += 1

        return {
            'total_files': total_count,
            'total_size_mb': total_size / (1024 * 1024),
        }
