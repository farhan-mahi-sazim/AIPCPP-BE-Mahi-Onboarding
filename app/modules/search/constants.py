import os

DEFAULT_SEARCH_LIMIT = 10
DEFAULT_SEARCH_OFFSET = 0
MAX_SEARCH_LIMIT = 100

SYNTHESIS_TIMEOUT_SECONDS = int(os.getenv("SYNTHESIS_TIMEOUT_SECONDS", "15"))
SYNTHESIS_MAX_CHUNKS = int(os.getenv("SYNTHESIS_MAX_CHUNKS", "5"))
SYNTHESIS_PROMPT_TEMPLATE = """You are a helpful assistant answering questions based on provided document excerpts.

Given the user's question and the most relevant excerpts from documents, provide a direct, concise answer (2-3 sentences maximum).

Rules:
- Answer only based on the provided excerpts
- If the excerpts don't contain enough information, say "I couldn't find a clear answer in the available documents."
- Be specific and reference key details from the excerpts
- Do not make up information

User Question: {query}

Relevant Document Excerpts:
{excerpts}

Direct Answer:"""

STOP_WORDS = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "am",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "has",
    "have",
    "here",
    "how",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "just",
    "may",
    "might",
    "more",
    "most",
    "no",
    "nor",
    "not",
    "of",
    "on",
    "once",
    "only",
    "or",
    "other",
    "our",
    "same",
    "should",
    "so",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "very",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "why",
    "will",
    "with",
    "would",
    "your",
}


class SearchError:
    EMPTY_QUERY = "Search query cannot be empty"
    EMBEDDING_FAILED = "Failed to generate embedding for query"
    INVALID_LIMIT = f"Limit must be between 1 and {MAX_SEARCH_LIMIT}"
    SYNTHESIS_FAILED = "Failed to generate synthesis answer"
