from pathlib import Path
from loguru import logger


def setup_logging() -> None:
    Path("logs").mkdir(exist_ok=True)
    logger.remove()
    logger.add("logs/api.log", rotation="10 MB", level="INFO")
    logger.add("logs/error.log", rotation="10 MB", level="ERROR")
