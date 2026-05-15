import functools
import hashlib
import logging
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from pydantic import BaseModel

from app.common.cache.constants import CACHE_DEFAULT_TTL
from app.common.cache.services import CacheService, get_cache_service
from app.config.settings import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _generate_cache_key(
    prefix: str,
    *args: Any,
    **kwargs: Any,
) -> str:
    key_parts = [prefix]

    for arg in args:
        if arg is not None:
            if hasattr(arg, "__class__") and arg.__class__.__name__ in ("ContentService", "DocumentService", "UserService", "VersionService"):
                continue
            key_parts.append(str(arg))

    for k, v in sorted(kwargs.items()):
        if v is not None:
            key_parts.append(f"{k}={v}")

    key_string = ":".join(key_parts)

    if len(key_string) > 200:
        hash_suffix = hashlib.md5(key_string.encode()).hexdigest()
        key_string = f"{prefix}:{hash_suffix}"

    return key_string


def cached(
    prefix: str,
    ttl: int = CACHE_DEFAULT_TTL,
    key_builder: Callable[..., str] | None = None,
) -> Callable[[Callable[..., Coroutine[Any, Any, T]]], Callable[..., Coroutine[Any, Any, T]]]:
    def decorator(
        func: Callable[..., Coroutine[Any, Any, T]],
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            if not settings.CACHE_ENABLED:
                return await func(*args, **kwargs)

            cache_service: CacheService | None = None

            try:
                cache_service = await get_cache_service()
            except Exception as e:
                logger.debug("Cache service unavailable: %s", str(e))

            if cache_service is None:
                return await func(*args, **kwargs)

            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                cache_key = _generate_cache_key(prefix, *args, **kwargs)

            cached_value = await cache_service.get(cache_key)
            if cached_value is not None:
                logger.debug("Cache hit for key: %s", cache_key)
                return cached_value

            result = await func(*args, **kwargs)

            if result is not None:
                try:
                    serialized = result if isinstance(result, BaseModel) else result
                    await cache_service.set(cache_key, serialized, ttl)
                except TypeError:
                    serialized = result.model_dump() if isinstance(result, BaseModel) else result
                    await cache_service.set(cache_key, serialized, ttl)
                logger.debug(
                    "Cache miss, stored result for key: %s (TTL: %ds)", cache_key, ttl
                )

            return result

        return wrapper

    return decorator


def cache_invalidate(prefix: str) -> Callable[[Callable[..., Coroutine[Any, Any, T]]], Callable[..., Coroutine[Any, Any, T]]]:
    def decorator(
        func: Callable[..., Coroutine[Any, Any, T]],
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            result = await func(*args, **kwargs)

            if not settings.CACHE_ENABLED:
                return result

            cache_service: CacheService | None = None
            try:
                cache_service = await get_cache_service()
            except Exception:
                pass

            if cache_service is not None:
                await cache_service.invalidate_prefix(prefix)
                logger.debug("Cache invalidated for prefix: %s", prefix)

            return result

        return wrapper

    return decorator


def cache_invalidate_on_args(
    prefix: str,
    arg_index: int = 0,
) -> Callable[[Callable[..., Coroutine[Any, Any, T]]], Callable[..., Coroutine[Any, Any, T]]]:
    def decorator(
        func: Callable[..., Coroutine[Any, Any, T]],
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            result = await func(*args, **kwargs)

            if not settings.CACHE_ENABLED:
                return result

            cache_service: CacheService | None = None
            try:
                cache_service = await get_cache_service()
            except Exception:
                pass

            if cache_service is not None:
                arg_value = args[arg_index] if len(args) > arg_index else kwargs.get("document_id")
                if arg_value:
                    cache_key = _generate_cache_key(prefix, arg_value)
                    await cache_service.delete(cache_key)
                    logger.debug("Cache invalidated for key: %s", cache_key)

            return result

        return wrapper

    return decorator
