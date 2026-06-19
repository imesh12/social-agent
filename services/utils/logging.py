import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def get_rotating_logger(name: str, filename: str) -> logging.Logger:
    """Return a logger writing to storage/logs with rotation."""
    logger = logging.getLogger(name)
    log_path = Path("storage/logs") / filename
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if not any(
        isinstance(handler, RotatingFileHandler)
        and getattr(handler, "baseFilename", None) == str(log_path.resolve())
        for handler in logger.handlers
    ):
        handler = RotatingFileHandler(
            log_path,
            maxBytes=10_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
        logger.addHandler(handler)

    logger.setLevel(logging.INFO)
    logger.propagate = True
    return logger
