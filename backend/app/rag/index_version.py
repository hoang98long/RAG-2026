"""Shared v5 signature. Changing this signature requires a deliberate reindex."""
import hashlib
import json


def collection_name(settings):
    signature = json.dumps({'version': 5, 'embedding': settings.embedding_model,
                            'instruction': settings.embedding_query_instruction,
                            'chunk_size': settings.chunk_size,
                            'chunk_overlap': settings.chunk_overlap}, sort_keys=True)
    return 'documents_v5_' + hashlib.sha256(signature.encode()).hexdigest()[:16]
