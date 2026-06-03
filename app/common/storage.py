import logging
import typing

import boto3
from botocore.client import Config

from app.config.settings import settings

logger = logging.getLogger(__name__)


UploadCallback = typing.Callable[[int], None]  # (bytes_transferred,)


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
        self,
        file_obj: typing.BinaryIO,
        s3_key: str,
        content_type: str,
        max_size: int | None = None,
        progress_callback: UploadCallback | None = None,
    ) -> str:
        """
        Uploads a file-like object to S3 and returns the s3_key.
        If max_size is provided, validates size during streaming without buffering.
        If progress_callback is provided, it will be called with (bytes_transferred,).
        """
        self._ensure_bucket_exists()

        if max_size:
            file_obj = self._create_size_limited_wrapper(file_obj, max_size)

        try:
            if progress_callback:
                self.s3.upload_fileobj(
                    file_obj,
                    self.bucket_name,
                    s3_key,
                    ExtraArgs={"ContentType": content_type},
                    Callback=progress_callback,
                )
            else:
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

    def _create_size_limited_wrapper(
        self, file_obj: typing.BinaryIO, max_size: int
    ) -> typing.BinaryIO:
        """
        Creates a wrapper that validates file size during streaming.
        Raises ValueError if max_size is exceeded.
        """
        bytes_uploaded = [0]  # Use list for mutable reference in nested function

        class SizeLimitedFile:
            def read(self, size: int = -1) -> bytes:
                chunk = file_obj.read(size)
                bytes_uploaded[0] += len(chunk)
                if bytes_uploaded[0] > max_size:
                    raise ValueError(f"File exceeded maximum size of {max_size} bytes")
                return chunk

            def __getattr__(self, name: str):
                # Delegate other attributes to wrapped object
                return getattr(file_obj, name)

        return SizeLimitedFile()  # type: ignore

    def get_file_content(self, s3_key: str) -> bytes:
        self._ensure_bucket_exists()
        try:
            response = self.s3.get_object(Bucket=self.bucket_name, Key=s3_key)
            return response["Body"].read()
        except Exception as e:
            logger.error("Failed to download file from S3: %s", e)
            raise e

    def get_presigned_url(self, s3_key: str, expires_in: int = 3600) -> str:
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

    def delete_file(self, s3_key: str) -> None:
        self._ensure_bucket_exists()
        try:
            self.s3.delete_object(Bucket=self.bucket_name, Key=s3_key)
            logger.info("File deleted from S3: %s", s3_key)
        except Exception as e:
            logger.error("Failed to delete file from S3: %s", e)
            raise e


def get_storage_service() -> StorageService:
    return StorageService()
