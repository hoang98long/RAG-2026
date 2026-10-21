"""Read-only deployment checks. Does not open Chroma, ingest, repair or create DBs."""
import argparse
import json
import sqlite3
from contextlib import closing, ExitStack
from pathlib import Path
from sqlalchemy.engine import make_url
from app.core.config import get_settings
from app.rag.index_version import collection_name
from app.services.readiness import model_status


def _read_only(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=3)


def check_storage(settings, scope):
    database = make_url(settings.public_database_url if scope == 'public' else settings.database_url)
    root = settings.scope_upload_path(scope).resolve()
    index = Path(settings.public_chroma_dir if scope == 'public' else settings.chroma_dir)
    lexical_path = index / 'lexical' / (collection_name(settings) + '.sqlite3')
    result = dict(scope=scope, ready=False, documents=0, files_missing=0, files_outside_root=0,
                  unindexed_documents=0, orphan_index_documents=0, collection=collection_name(settings))
    if database.get_backend_name() != 'sqlite' or not database.database:
        return {**result, 'issue': 'metadata_backend_not_supported'}
    if not Path(database.database).is_file():
        return {**result, 'issue': 'metadata_missing_verify_storage_path'}
    try:
        with ExitStack() as stack:
            db = stack.enter_context(closing(_read_only(database.database)))
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                return {**result, 'issue': 'metadata_integrity_failed'}
            lexical = stack.enter_context(closing(_read_only(lexical_path))) if lexical_path.is_file() else None
            dirty = bool(lexical.execute("SELECT value FROM state WHERE key='dirty'").fetchone()[0]) if lexical else False
            for identifier, stored_path in db.execute('SELECT id, filepath FROM documents'):
                result['documents'] += 1
                path = Path(stored_path).resolve()
                if not path.is_relative_to(root):
                    result['files_outside_root'] += 1
                elif not path.is_file():
                    result['files_missing'] += 1
                if lexical is None or lexical.execute('SELECT 1 FROM chunks WHERE document_id=? LIMIT 1', (identifier,)).fetchone() is None:
                    result['unindexed_documents'] += 1
            if lexical:
                for identifier, in lexical.execute('SELECT DISTINCT document_id FROM chunks'):
                    if db.execute('SELECT 1 FROM documents WHERE id=?', (identifier,)).fetchone() is None:
                        result['orphan_index_documents'] += 1
            missing_vector = result['documents'] > 0 and not (index / 'chroma.sqlite3').is_file()
            result['ready'] = not (dirty or missing_vector or any(result[key] for key in
                ('files_missing', 'files_outside_root', 'unindexed_documents', 'orphan_index_documents')))
            result['issue'] = ('lexical_rebuild_pending' if dirty else 'vector_database_missing' if missing_vector else
                               'storage_mismatch' if not result['ready'] else 'empty_corpus' if not result['documents'] else None)
    except (sqlite3.Error, OSError, TypeError, ValueError):
        result.update(ready=False, issue='storage_check_failed')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=['private', 'public', 'all'], default='all')
    parser.add_argument('--skip-models', action='store_true', help='Only inspect local storage and access configuration')
    args = parser.parse_args()
    settings = get_settings()
    scopes = ['private', 'public'] if args.scope == 'all' else [args.scope]
    storage = [check_storage(settings, scope) for scope in scopes]
    result = dict(storage=storage, internal_access_configured=bool(settings.internal_access_token.get_secret_value().strip()),
                  model_probe_skipped=args.skip_models,
                  limitations='Does not verify vector contents, inference quality, available RAM/VRAM, OpenAI connectivity or TLS.')
    models_ready = True
    if not args.skip_models:
        models, checks = model_status(settings)
        result.update(models=models, dependencies=checks)
        models_ready = all(checks.values())
    result['ready'] = models_ready and result['internal_access_configured'] and all(item['ready'] for item in storage)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result['ready'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
