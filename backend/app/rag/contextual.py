"""Context derives only from source headings and filename, never generated facts."""


def retrieval_text(filename: str, content: str, metadata: dict) -> str:
    labels = [f"Document: {filename}"]
    if metadata.get("section"):
        labels.append(f"Section: {metadata['section']}")
    if metadata.get("table_header"):
        labels.append(f"Table columns: {metadata['table_header']}")
    return "\n".join(labels) + "\n\n" + content
