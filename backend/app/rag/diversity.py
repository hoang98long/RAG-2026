"""Bounded rank-based MMR preselection and fair expansion across source sections."""
from collections import OrderedDict, deque
from app.rag.retrieval import tokenize
from app.rag.sections import section_key


def _shingles(item: dict) -> set[tuple[str, ...]]:
    # Use source text only; filenames/boilerplate metadata must not dominate novelty.
    tokens = tokenize(item.get('content', ''))
    return set(zip(tokens, tokens[1:])) if len(tokens) > 1 else {(token,) for token in tokens}


def mmr_pool(candidates: list[dict], limit: int, relevance_weight: float = 0.75) -> list[dict]:
    """Seeded MMR using RRF rank as relevance proxy and word-bigram Jaccard novelty.

    Preserve the leading quarter and original order of selected candidates so
    grader ties keep their relevance order. No approximate passage is deleted
    from storage, merged, or rewritten. Only the bounded grader pool changes.
    """
    if limit <= 0:
        return []
    if len(candidates) <= limit or relevance_weight >= 1:
        return candidates[:limit]
    # Avoid scanning the whole merged result or promoting arbitrarily deep hits.
    window = candidates[:limit * 4]
    features = [_shingles(item) for item in window]
    selected = list(range(max(1, limit // 4)))
    remaining = set(range(len(selected), len(window)))
    redundancy = dict.fromkeys(remaining, 0.0)

    def update(chosen):
        for index in remaining:
            a, b = features[index], features[chosen]
            common = len(a & b)
            similarity = common / (len(a) + len(b) - common) if a or b else 0.0
            redundancy[index] = max(redundancy[index], similarity)

    for chosen in selected:
        update(chosen)
    while remaining and len(selected) < limit:
        # This rank proxy has no calibrated probability interpretation.
        chosen = max(remaining, key=lambda index: (
            relevance_weight * 61 / (61 + index) - (1 - relevance_weight) * redundancy[index], -index))
        selected.append(chosen)
        remaining.remove(chosen)
        update(chosen)
    return [window[index] for index in sorted(selected)]


def interleave_sections(items: list[dict]) -> list[dict]:
    """Round-robin distinct scope/document/section queues without text deduplication."""
    groups = OrderedDict()
    for item in items:
        key = (item['scope'], item['document_id'], section_key(item.get('section', '')))
        groups.setdefault(key, deque()).append(item)
    active, result = deque(groups.values()), []
    while active:
        group = active.popleft()
        result.append(group.popleft())
        if group:
            active.append(group)
    return result
