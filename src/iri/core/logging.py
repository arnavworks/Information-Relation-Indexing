"""Small, dependency-free logging configuration for API and worker processes."""

import logging


def configure_logging(level: str) -> None:
    """Configure structured-friendly logs without owning handler lifecycles."""

    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
