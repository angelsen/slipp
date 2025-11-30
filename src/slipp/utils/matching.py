"""Fuzzy string matching utilities."""

from difflib import SequenceMatcher


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

        if query_clean in candidate_clean or candidate_clean in query_clean:
            score = 0.9 + (len(query_clean) / len(candidate_clean)) * 0.1
            if score > best_score:
                best_score = score
                best_match = candidate
            continue

        ratio = SequenceMatcher(None, query_clean, candidate_clean).ratio()
        if ratio >= threshold and ratio > best_score:
            best_score = ratio
            best_match = candidate

    return best_match


def get_suggestions(
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
        >>> get_suggestions("synapze", ["matrix-synapse", "caddy", "postgres"])
        ['matrix-synapse']
    """
    query_clean = query.lower()
    scored: list[tuple[float, str]] = []

    for candidate in candidates:
        candidate_clean = candidate.lower()

        if query_clean == candidate_clean:
            continue

        if query_clean in candidate_clean or candidate_clean in query_clean:
            score = 0.9
        else:
            score = SequenceMatcher(None, query_clean, candidate_clean).ratio()

        if score >= threshold:
            scored.append((score, candidate))

    scored.sort(key=lambda x: x[0], reverse=True)

    return [candidate for _, candidate in scored[:max_results]]
