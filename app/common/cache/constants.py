from enum import IntEnum, StrEnum


class ECacheKeyPrefix(StrEnum):
    CONTENT_SUMMARIES = "content:summaries"
    CONTENT_SUMMARY = "content:summary"
    CONTENT_DOCUMENT = "content:document"
    SEARCH_RESULTS = "search:results"
    VERSION = "version"
    GENERIC = "cache"


class ECacheTTL(IntEnum):
    SHORT = 60
    MEDIUM = 300
    LONG = 3600
    VERY_LONG = 86400


CACHE_DEFAULT_TTL = ECacheTTL.MEDIUM.value
CACHE_CONTENT_TTL = ECacheTTL.LONG.value
CACHE_VERSION_TTL = ECacheTTL.LONG.value
CACHE_SEARCH_TTL = ECacheTTL.MEDIUM.value
