import logging
import os

LOG_LEVEL_ENV_VAR = "CRONJOB_LOCK_LOG_LEVEL"
_DEFAULT_LEVEL = "WARNING"
_VALID_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


def configure_cli_logging() -> None:
    raw = os.environ.get(LOG_LEVEL_ENV_VAR, _DEFAULT_LEVEL).upper()
    level = raw if raw in _VALID_LEVELS else _DEFAULT_LEVEL
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("dislock")
    if raw != level:
        logger.warning(
            "Invalid %s=%r, defaulting to %s.",
            LOG_LEVEL_ENV_VAR,
            raw,
            _DEFAULT_LEVEL,
        )
