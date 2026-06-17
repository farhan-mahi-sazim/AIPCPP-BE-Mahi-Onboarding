import hashlib
import json
import logging
from typing import Any, TypeVar

from fastapi import Request
from pydantic import BaseModel

from app.common.cache.constants import CACHE_DEFAULT_TTL
from app.common.cache.services import get_cache_service
from app.config.settings import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class CacheResponse(BaseModel):
    cached: bool
    data: Any


async def get_cached_response(
    key: str,
) -> tuple[Any, bool]:
    if not settings.CACHE_ENABLED:
        return None, False

    cache_service = await get_cache_service()
    if cache_service is None:
        return None, False

    cached_data = await cache_service.get(key)
    if cached_data is not None:
        logger.debug("Returning cached response for key: %s", key)
        return cached_data, True

    return None, False


async def set_cached_response(
    key: str,
    data: Any,
    ttl: int = CACHE_DEFAULT_TTL,
) -> bool:
    if not settings.CACHE_ENABLED:
        return False

    cache_service = await get_cache_service()
    if cache_service is None:
        return False

    return await cache_service.set(key, data, ttl)


def generate_cache_key_from_request(
    request: Request,
    prefix: str,
    include_query: bool = True,
) -> str:
    path = request.url.path
    query_params = dict(request.query_params) if include_query else {}

    key_parts = [prefix, path]

    if query_params:
        sorted_params = sorted(query_params.items())
        params_str = json.dumps(sorted_params)
        params_hash = hashlib.md5(params_str.encode()).hexdigest()[:16]
        key_parts.append(params_hash)

    return ":".join(key_parts)


class CacheInvalidator:
    def __init__(self, prefixes: list[str]) -> None:
        self.prefixes = prefixes

    async def invalidate(self) -> int:
        if not settings.CACHE_ENABLED:
            return 0

        cache_service = await get_cache_service()
        if cache_service is None:
            return 0

        total_deleted = 0
        for prefix in self.prefixes:
            count = await cache_service.invalidate_prefix(prefix)
            total_deleted += count

        return total_deleted


def create_cache_invalidator(*prefixes: str) -> CacheInvalidator:
    return CacheInvalidator(list(prefixes))
