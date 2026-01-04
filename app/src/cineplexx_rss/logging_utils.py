import logging
import sys
import uuid
from contextvars import ContextVar

_RUN_ID: ContextVar[str] = ContextVar("run_id", default="unknown")


class RunIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = _RUN_ID.get() or "unknown"
        return True


def new_run_id() -> str:
    return uuid.uuid4().hex[:8]


def set_run_id(run_id: str) -> None:
    _RUN_ID.set(run_id)


def setup_logging(log_level: str) -> logging.Logger:
    level = getattr(logging, log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers on repeated setup.
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s run_id=%(run_id)s %(message)s"
    )
    handler.setFormatter(formatter)
    handler.addFilter(RunIdFilter())
    root.addHandler(handler)

    return root
