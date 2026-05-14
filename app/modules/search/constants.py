DEFAULT_SEARCH_LIMIT = 10
DEFAULT_SEARCH_OFFSET = 0
MAX_SEARCH_LIMIT = 100


class SearchError:
    EMPTY_QUERY = "Search query cannot be empty"
    EMBEDDING_FAILED = "Failed to generate embedding for query"
    INVALID_LIMIT = f"Limit must be between 1 and {MAX_SEARCH_LIMIT}"
