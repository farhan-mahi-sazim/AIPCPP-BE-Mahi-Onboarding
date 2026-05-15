import logging

import redis.asyncio as redis
from redis.asyncio import Redis

from app.config.settings import settings

logger = logging.getLogger(__name__)


class CacheConnectionManager:
    _instance: Redis | None = None
    _is_available: bool = False

    @classmethod
    async def get_connection(cls) -> Redis | None:
        if not settings.CACHE_ENABLED:
            logger.debug("Cache is disabled via settings")
            return None

        if cls._instance is not None:
            return cls._instance

        try:
            cls._instance = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
            await cls._instance.ping()
            cls._is_available = True
            logger.info("Redis cache connected successfully")
            return cls._instance
        except Exception as e:
            logger.warning("Redis cache unavailable: %s", str(e))
            cls._is_available = False
            return None

    @classmethod
    async def close(cls) -> None:
        if cls._instance is not None:
            await cls._instance.close()
            cls._instance = None
            cls._is_available = False
            logger.info("Redis cache connection closed")

    @classmethod
    def is_available(cls) -> bool:
        return cls._is_available


async def get_cache_client() -> Redis | None:
    return await CacheConnectionManager.get_connection()
