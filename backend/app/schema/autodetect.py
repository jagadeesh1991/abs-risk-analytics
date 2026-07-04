"""Fuzzy matching of raw file columns to canonical schema fields."""
import re
from difflib import SequenceMatcher

from .canonical import FIELDS


def _norm(name: str) -> str:
    """Lowercase and strip everything that isn't a letter or digit."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def suggest_mapping(columns: list[str]) -> dict[str, str]:
    """Return {file_column: canonical_field} suggestions for a list of raw columns.

    Exact alias matches win; otherwise the best fuzzy match above a threshold.
    Each canonical field is suggested at most once.
    """
    # canonical field -> set of normalized accepted names
    candidates: list[tuple[str, str]] = []  # (normalized alias, field name)
    for f in FIELDS:
        candidates.append((_norm(f.name), f.name))
        candidates.append((_norm(f.label), f.name))
        for a in f.aliases:
            candidates.append((_norm(a), f.name))

    mapping: dict[str, str] = {}
    used_fields: set[str] = set()

    # Pass 1: exact normalized matches
    for col in columns:
        n = _norm(col)
        for alias, fname in candidates:
            if n == alias and fname not in used_fields:
                mapping[col] = fname
                used_fields.add(fname)
                break

    # Pass 2: fuzzy matches for the rest
    for col in columns:
        if col in mapping:
            continue
        n = _norm(col)
        if not n:
            continue
        best_score, best_field = 0.0, None
        for alias, fname in candidates:
            if fname in used_fields or not alias:
                continue
            score = SequenceMatcher(None, n, alias).ratio()
            # substring containment is a strong signal for column names
            if alias in n or n in alias:
                score = max(score, 0.87)
            if score > best_score:
                best_score, best_field = score, fname
        if best_field and best_score >= 0.82:
            mapping[col] = best_field
            used_fields.add(best_field)

    return mapping
