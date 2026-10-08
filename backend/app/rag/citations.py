"""Validate citation identifiers, not the semantic truth of cited claims."""
import re


def citations_valid(text: str, sources: list[dict]) -> bool:
    visible = re.sub(r'```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`]*`', '', text)
    cited = set(re.findall(r'\[(S\d+)\]', visible))
    allowed = {source['source_id'] for source in sources}
    return bool(text.strip() and cited) and cited.issubset(allowed)
