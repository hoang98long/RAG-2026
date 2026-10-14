"""Citation syntax and exact quote checks. These do not prove semantic entailment."""
import re
import unicodedata


def visible_text(text: str) -> str:
    return re.sub(r'```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`]*`', '', text)


def cited_ids(text: str) -> list[str]:
    groups = re.findall(r'\[\s*S\d+(?:\s*[,;]\s*S\d+)*\s*\]', visible_text(text))
    return list(dict.fromkeys(identifier for group in groups for identifier in re.findall(r'S\d+', group)))


def citations_valid(text: str, sources: list[dict]) -> bool:
    cited = set(cited_ids(text))
    return bool(text.strip() and cited) and cited.issubset({source['source_id'] for source in sources})


def normalized_text(text: str) -> str:
    return ' '.join(unicodedata.normalize('NFC', text).casefold().split())


def quote_support_valid(claim: str, quote: str, answer: str, source: str) -> bool:
    claim, quote = normalized_text(claim), normalized_text(quote)
    return len(claim) >= 3 and len(quote) >= 3 and claim in normalized_text(answer) and quote in normalized_text(source)
