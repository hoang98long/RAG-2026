"""Evaluate filename-level retrieval recall and MRR without calling the LLM."""
import argparse
import json
from pathlib import Path
from app.core.config import get_settings
from app.rag.vector_store import get_vector_store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    cases = [json.loads(line) for line in args.dataset.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if not cases:
        parser.error("Dataset must contain at least one case")
    for case in cases:
        expected = case.get("expected_documents")
        if not isinstance(case.get("question"), str) or not case["question"].strip():
            parser.error("Each case requires a nonempty question")
        if not isinstance(expected, list) or not expected or not all(isinstance(x, str) and x for x in expected):
            parser.error("Each case requires a nonempty list of expected_documents")
    store = get_vector_store()
    recalls, reciprocals = [], []
    for case in cases:
        sources = store.search(case["question"], get_settings().top_k)
        expected = set(case["expected_documents"])
        retrieved = [source["document"] for source in sources]
        recalls.append(len(expected & set(retrieved)) / len(expected))
        reciprocals.append(next((1 / rank for rank, name in enumerate(retrieved, 1) if name in expected), 0))
        print(json.dumps({"question": case["question"], "retrieved": retrieved, "recall": recalls[-1]}, ensure_ascii=False))
    print(json.dumps({"cases": len(cases), "top_k": get_settings().top_k,
                      "mean_document_recall": sum(recalls) / len(cases),
                      "mrr": sum(reciprocals) / len(cases)}, indent=2))


if __name__ == "__main__":
    main()
