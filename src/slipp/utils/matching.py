"""Fuzzy string matching utilities."""

from difflib import SequenceMatcher


def _score(query_clean: str, candidate_clean: str) -> float:
    """Similarity score: length-weighted for substring containment, else SequenceMatcher ratio."""
    if not query_clean or not candidate_clean:
        return 0.0
    if query_clean in candidate_clean or candidate_clean in query_clean:
        return min(1.0, 0.9 + (len(query_clean) / len(candidate_clean)) * 0.1)
    return SequenceMatcher(None, query_clean, candidate_clean).ratio()


def fuzzy_match(
    query: str,
    candidates: list[str],
    threshold: float = 0.6,
) -> str | None:
    """Find best fuzzy match from candidates.

    Match priority:
    1. Exact match (case-insensitive)
    2. Substring match (query in candidate or vice versa)
    3. Similarity ratio >= threshold

    Args:
        query: Search term (e.g., "synapse")
        candidates: List of possible matches (e.g., ["matrix-synapse", "caddy"])
        threshold: Minimum similarity ratio (0.0-1.0)

    Returns:
        Best matching candidate, or None if no match

    Example:
        >>> fuzzy_match("synapse", ["matrix-synapse", "caddy"])
        'matrix-synapse'
        >>> fuzzy_match("synapze", ["matrix-synapse", "caddy"])
        'matrix-synapse'
    """
    query_clean = query.lower()

    best_match: str | None = None
    best_score = 0.0

    for candidate in candidates:
        candidate_clean = candidate.lower()

        if query_clean == candidate_clean:
            return candidate

        score = _score(query_clean, candidate_clean)
        if score >= threshold and score > best_score:
            best_score = score
            best_match = candidate

    return best_match


def fuzzy_suggestions(
    query: str,
    candidates: list[str],
    max_results: int = 3,
    threshold: float = 0.4,
) -> list[str]:
    """Get ranked suggestions for typo correction.

    Returns candidates sorted by similarity to query.

    Args:
        query: Search term
        candidates: List of possible matches
        max_results: Maximum suggestions to return
        threshold: Minimum similarity to include

    Returns:
        List of suggestions, best match first

    Example:
        >>> fuzzy_suggestions("synapze", ["matrix-synapse", "caddy", "postgres"])
        ['matrix-synapse']
    """
    query_clean = query.lower()
    scored: list[tuple[float, str]] = []

    for candidate in candidates:
        candidate_clean = candidate.lower()

        if query_clean == candidate_clean:
            continue

        score = _score(query_clean, candidate_clean)
        if score >= threshold:
            scored.append((score, candidate))

    scored.sort(key=lambda x: x[0], reverse=True)

    return [candidate for _, candidate in scored[:max_results]]
