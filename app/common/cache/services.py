import json
import logging
import uuid as uuid_module
from collections.abc import Callable
from datetime import date, datetime
from typing import Any, TypeVar

from pydantic import BaseModel
from redis.asyncio import Redis

from app.common.cache.connection import CacheConnectionManager
from app.common.cache.constants import CACHE_DEFAULT_TTL

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _json_encoder(obj: Any) -> str:
    if isinstance(obj, (uuid_module.UUID, datetime, date)):
        return obj.isoformat() if hasattr(obj, "isoformat") else str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class CacheService:
    def __init__(self, redis_client: Redis | None = None) -> None:
        self._client = redis_client

    async def _get_client(self) -> Redis | None:
        if self._client is not None:
            return self._client
        return await CacheConnectionManager.get_connection()

    async def get(self, key: str) -> Any | None:
        client = await self._get_client()
        if client is None:
            return None

        try:
            value = await client.get(key)
            if value is None:
                return None
            return json.loads(value)
        except Exception as e:
            logger.warning("Cache get failed for key %s: %s", key, str(e))
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = CACHE_DEFAULT_TTL,
    ) -> bool:
        client = await self._get_client()
        if client is None:
            return False

        try:
            if isinstance(value, BaseModel):
                serialized = value.model_dump(mode="json")
            else:
                serialized = value
            await client.setex(key, ttl, json.dumps(serialized, default=_json_encoder))
            return True
        except Exception as e:
            logger.warning("Cache set failed for key %s: %s", key, str(e))
            return False

    async def delete(self, key: str) -> bool:
        client = await self._get_client()
        if client is None:
            return False

        try:
            await client.delete(key)
            return True
        except Exception as e:
            logger.warning("Cache delete failed for key %s: %s", key, str(e))
            return False

    async def delete_pattern(self, pattern: str) -> int:
        client = await self._get_client()
        if client is None:
            return 0

        try:
            keys = []
            async for key in client.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                return await client.delete(*keys)
            return 0
        except Exception as e:
            logger.warning(
                "Cache delete_pattern failed for pattern %s: %s", pattern, str(e)
            )
            return 0

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Any],
        ttl: int = CACHE_DEFAULT_TTL,
    ) -> Any:
        cached = await self.get(key)
        if cached is not None:
            return cached

        value = await factory() if callable(factory) else factory

        if value is not None:
            await self.set(key, value, ttl)

        return value

    async def exists(self, key: str) -> bool:
        client = await self._get_client()
        if client is None:
            return False

        try:
            return await client.exists(key) > 0
        except Exception:
            return False

    async def invalidate_prefix(self, prefix: str) -> int:
        return await self.delete_pattern(f"{prefix}*")


_cache_service: CacheService | None = None


async def get_cache_service() -> CacheService:
    global _cache_service
    if _cache_service is None:
        redis_client = await CacheConnectionManager.get_connection()
        _cache_service = CacheService(redis_client)
    return _cache_service
