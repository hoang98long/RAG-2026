"""BM25 with positive IDF, reciprocal rank fusion and duplicate suppression."""
import math
import re
import unicodedata
from collections import Counter, defaultdict


def tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", unicodedata.normalize("NFC", text).casefold())


class BM25Index:
    def __init__(self, texts: list[str]):
        terms = [Counter(tokenize(text)) for text in texts]
        self.lengths = [sum(item.values()) for item in terms]
        self.average_length = sum(self.lengths) / max(len(texts), 1) or 1
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for index, item in enumerate(terms):
            for term, frequency in item.items():
                self.postings[term].append((index, frequency))

    def search(self, query: str, limit: int) -> list[int]:
        scores: dict[int, float] = defaultdict(float)
        count = len(self.lengths)
        for term in set(tokenize(query)):
            postings = self.postings.get(term, [])
            idf = math.log(1 + (count - len(postings) + 0.5) / (len(postings) + 0.5))
            for index, frequency in postings:
                norm = 1.5 * (0.25 + 0.75 * self.lengths[index] / self.average_length)
                scores[index] += idf * frequency * 2.5 / (frequency + norm)
        return sorted(scores, key=lambda index: (-scores[index], index))[:limit]


def fuse_rankings(*rankings: list[str]) -> list[tuple[str, float]]:
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, identifier in enumerate(dict.fromkeys(ranking), start=1):
            scores[identifier] += 1 / (60 + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def select_sources(candidates: list[dict], limit: int, budget: int) -> list[dict]:
    selected: list[dict] = []
    seen: set[str] = set()
    per_document: Counter[str] = Counter()
    used = 0
    for candidate in candidates:
        document_id = candidate.get("document_id") or candidate["document"]
        if per_document[document_id] >= 2:
            continue
        # Exact normalized duplicates only: don't erase nearly identical clauses
        # that differ in a crucial number, negation or effective date.
        key = " ".join(unicodedata.normalize("NFC", candidate["content"]).casefold().split())
        if key in seen:
            continue
        cost = len(candidate["content"]) + len(candidate["document"]) + 100
        if used + cost > budget:
            continue
        selected.append({**candidate, "source_id": f"S{len(selected) + 1}"})
        seen.add(key)
        per_document[document_id] += 1
        used += cost
        if len(selected) >= limit:
            break
    return selected
