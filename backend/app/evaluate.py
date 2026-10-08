"""Evaluate retrieval at document/page/chunk granularity, including no-source cases."""
import argparse
import json
import math
import statistics
import time
from pathlib import Path
from app.core.config import get_settings
from app.rag.vector_store import get_vector_store


def expected_sources(case: dict) -> list[dict]:
    if not isinstance(case, dict) or not isinstance(case.get('question'), str) or not case['question'].strip():
        raise ValueError('Each case requires a nonempty question')
    if 'expected_sources' in case:
        labels = case['expected_sources']
        if not isinstance(labels, list):
            raise ValueError('expected_sources must be a list (empty for unanswerable queries)')
        for label in labels:
            if not isinstance(label, dict) or not any(isinstance(label.get(key), str) and label[key] for key in ('document', 'document_id')):
                raise ValueError('Each expected source requires document or document_id')
            for key, minimum in [('page', 1), ('chunk_index', 0)]:
                if key in label and (type(label[key]) is not int or label[key] < minimum):
                    raise ValueError(f'Invalid {key} in expected source')
    elif 'expected_documents' in case:
        documents = case['expected_documents']
        if not isinstance(documents, list) or not all(isinstance(value, str) and value for value in documents):
            raise ValueError('expected_documents must be a list of filenames')
        labels = [{'document': value} for value in dict.fromkeys(documents)]
    else:
        raise ValueError('Each case requires expected_sources or expected_documents')
    return labels


def matches(source: dict, label: dict) -> bool:
    return all(source.get(key) == label[key] for key in ('document', 'document_id', 'page', 'chunk_index') if key in label)


def retrieval_metrics(sources: list[dict], labels: list[dict]) -> dict:
    if not labels:
        return {'recall': None, 'precision': None, 'reciprocal_rank': None, 'correct_abstention': not sources}
    hits = [any(matches(source, label) for label in labels) for source in sources]
    recall = sum(any(matches(source, label) for source in sources) for label in labels) / len(labels)
    return {'recall': recall, 'precision': sum(hits) / len(hits) if hits else 0,
            'reciprocal_rank': next((1 / rank for rank, hit in enumerate(hits, 1) if hit), 0),
            'correct_abstention': None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', type=Path)
    parser.add_argument('--hybrid-only', action='store_true', help='Disable reranking for an ablation run')
    parser.add_argument('--output', type=Path, help='Write all case results and configuration as JSON')
    args = parser.parse_args()
    try:
        cases = [json.loads(line) for line in args.dataset.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
        if not cases:
            raise ValueError('Dataset must contain at least one case')
        labels = [expected_sources(case) for case in cases]
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    store = get_vector_store()
    settings = get_settings()
    results = []
    for case, expected in zip(cases, labels):
        start = time.perf_counter()
        sources = store.search(case['question'], settings.top_k, use_rerank=not args.hybrid_only)
        elapsed = time.perf_counter() - start
        result = {'question': case['question'], 'expected_sources': expected,
                  'sources': sources, 'seconds': elapsed, **retrieval_metrics(sources, expected)}
        results.append(result)
        print(json.dumps({key: value for key, value in result.items() if key != 'sources'}, ensure_ascii=False))
    positive = [result for result in results if result['recall'] is not None]
    negative = [result for result in results if result['correct_abstention'] is not None]
    times = sorted(result['seconds'] for result in results)
    summary = {'cases': len(cases), 'answerable_cases': len(positive), 'unanswerable_cases': len(negative),
               'recall_at_k': statistics.mean(result['recall'] for result in positive) if positive else None,
               'precision_returned': statistics.mean(result['precision'] for result in positive) if positive else None,
               'mrr': statistics.mean(result['reciprocal_rank'] for result in positive) if positive else None,
               'retrieval_abstention_accuracy': statistics.mean(result['correct_abstention'] for result in negative) if negative else None,
               'mean_seconds': statistics.mean(times), 'p95_seconds': times[math.ceil(0.95 * len(times)) - 1],
               'fallback_cases': sum(any(source.get('rerank_method') == 'hybrid_fallback' for source in result['sources']) for result in results)}
    configuration = {key: getattr(settings, key) for key in ('llm_model', 'embedding_model', 'chunk_size', 'chunk_overlap',
                    'top_k', 'retrieval_candidates', 'max_context_chars', 'min_similarity', 'rerank_backend',
                    'rerank_model', 'rerank_candidates', 'rerank_min_grade', 'rerank_batch_size', 'llm_num_ctx',
                    'embedding_query_instruction', 'cross_encoder_model', 'cross_encoder_device',
                    'cross_encoder_max_length', 'cross_encoder_min_score')}
    configuration.update({'collection': store.collection.name, 'hybrid_only': args.hybrid_only, 'max_sources_per_document': 2})
    report = {'configuration': configuration, 'summary': summary, 'results': results}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'configuration': configuration, 'summary': summary}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
