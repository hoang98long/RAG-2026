from pathlib import Path
import sys
from loguru import logger


def setup_logging() -> None:
    Path('logs').mkdir(exist_ok=True)
    logger.remove()
    # Never include local variables or provider payloads in error reports.
    options = dict(backtrace=False, diagnose=False, level='INFO')
    logger.add(sys.stderr, **options)
    logger.add('logs/api.log', rotation='10 MB', retention='7 days', compression='gz', **options)
    logger.add('logs/error.log', rotation='10 MB', retention='7 days', compression='gz',
               backtrace=False, diagnose=False, level='ERROR')
