DEFAULT_SEARCH_LIMIT = 10
DEFAULT_SEARCH_OFFSET = 0
MAX_SEARCH_LIMIT = 3
SYNTHESIS_PROMPT_TEMPLATE = """You are a helpful assistant answering questions based on provided document excerpts.

Given the user's question and the most relevant excerpts from documents, provide a direct, informative answer.

Rules:
- Answer only based on the provided excerpts
- Be specific — reference actual details, comparisons, numbers, or names from the excerpts
- Structure as 3-5 complete, natural sentences
- If the excerpts don't contain enough information, say "I couldn't find a clear answer in the available documents."
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
