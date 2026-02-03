"""Utility functions and logging setup."""

import logging
import sys
from datetime import datetime
from pathlib import Path


def setup_logging(log_level: str = "INFO", log_file: str | None = None) -> logging.Logger:
    """Configure logging for the trading bot."""
    logger = logging.getLogger("kash")
    
    # Clear existing handlers to prevent duplicates
    if logger.handlers:
        logger.handlers.clear()
    
    logger.setLevel(getattr(logging, log_level.upper()))
    
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def format_price(price: float, decimals: int = 2) -> str:
    """Format price with appropriate decimal places."""
    return f"€{price:,.{decimals}f}"


def format_percent(value: float) -> str:
    """Format percentage value."""
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def timestamp_now() -> str:
    """Get current timestamp as ISO string."""
    return datetime.now().isoformat()


logger = setup_logging()
