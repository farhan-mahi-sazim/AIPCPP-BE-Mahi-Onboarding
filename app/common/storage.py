import boto3
from botocore.client import Config
from app.config.settings import settings
import logging

logger = logging.getLogger(__name__)


import typing


class StorageService:
    def __init__(self) -> None:
        self.s3 = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            use_ssl=settings.S3_USE_SSL,
            verify=settings.S3_USE_SSL,
        )
        self.bucket_name = settings.S3_BUCKET_NAME
        self._bucket_verified = False

    def _ensure_bucket_exists(self) -> None:
        if self._bucket_verified:
            return

        try:
            self.s3.head_bucket(Bucket=self.bucket_name)
        except self.s3.exceptions.ClientError:
            logger.info("Bucket %s not found. Creating...", self.bucket_name)
            self.s3.create_bucket(Bucket=self.bucket_name)
            logger.info("Bucket %s created successfully.", self.bucket_name)

        self._bucket_verified = True

    def upload_file(
        self, file_obj: typing.BinaryIO, s3_key: str, content_type: str
    ) -> str:
        """
        Uploads a file-like object to S3 and returns the s3_key.
        """
        self._ensure_bucket_exists()
        try:
            self.s3.upload_fileobj(
                file_obj,
                self.bucket_name,
                s3_key,
                ExtraArgs={"ContentType": content_type},
            )
            return s3_key
        except Exception as e:
            logger.error("Failed to upload file to S3: %s", e)
            raise e

    def get_file_content(self, s3_key: str) -> bytes:
        """
        Downloads a file from S3.
        """
        self._ensure_bucket_exists()
        try:
            response = self.s3.get_object(Bucket=self.bucket_name, Key=s3_key)
            return response["Body"].read()
        except Exception as e:
            logger.error("Failed to download file from S3: %s", e)
            raise e

    def get_presigned_url(self, s3_key: str, expires_in: int = 3600) -> str:
        """
        Generates a pre-signed URL for a file.
        """
        self._ensure_bucket_exists()
        try:
            return self.s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": s3_key},
                ExpiresIn=expires_in,
            )
        except Exception as e:
            logger.error("Failed to generate pre-signed URL: %s", e)
            raise e


def get_storage_service() -> StorageService:
    return StorageService()
