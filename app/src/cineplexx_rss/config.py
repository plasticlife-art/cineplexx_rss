from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
import logging
import os

load_dotenv()

@dataclass(frozen=True)
class Config:
    base_url: str
    location: str
    date_mode: str
    fixed_date: str
    timezone: str

    out_dir: Path
    rss_filename: str
    events_limit: int
    max_events_in_state: int
    telegram_channels: list[str]
    telegram_post_limit: int
    redis_url: str | None
    cache_enabled: bool
    film_cache_ttl_seconds: int
    cache_negative_ttl_seconds: int
    max_film_pages_concurrency: int

    feed_title: str
    feed_link: str
    feed_description: str

def load_config() -> Config:
    out_dir = Path(os.getenv("OUT_DIR", "./out"))
    out_dir.mkdir(parents=True, exist_ok=True)

    def _int(name: str, default: int) -> int:
        try:
            return int(os.getenv(name, str(default)).strip())
        except Exception:
            return default

    def _bool(name: str, default: bool) -> bool:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            return default
        val = raw.strip().lower()
        if val in ("1", "true", "yes", "on"):
            return True
        if val in ("0", "false", "no", "off"):
            return False
        logging.getLogger(__name__).warning(
            "invalid %s=%s, using default=%s",
            name,
            raw,
            default,
        )
        return default

    def _list(name: str) -> list[str]:
        raw = os.getenv(name, "")
        items = [x.strip() for x in raw.split(",") if x.strip()]
        return items

    max_events_in_state = _int("MAX_EVENTS_IN_STATE", 5000)
    if max_events_in_state <= 0:
        logging.getLogger(__name__).warning(
            "invalid MAX_EVENTS_IN_STATE=%s, using default=5000",
            os.getenv("MAX_EVENTS_IN_STATE", ""),
        )
        max_events_in_state = 5000

    redis_url = os.getenv("REDIS_URL", "").strip() or None
    cache_enabled = _bool("CACHE_ENABLED", bool(redis_url))
    film_cache_ttl_seconds = _int("CINEPLEXX_FILM_CACHE_TTL_SECONDS", 604800)
    if film_cache_ttl_seconds <= 0:
        logging.getLogger(__name__).warning(
            "invalid CINEPLEXX_FILM_CACHE_TTL_SECONDS=%s, using default=604800",
            os.getenv("CINEPLEXX_FILM_CACHE_TTL_SECONDS", ""),
        )
        film_cache_ttl_seconds = 604800
    cache_negative_ttl_seconds = _int("CINEPLEXX_CACHE_NEGATIVE_TTL_SECONDS", 3600)
    if cache_negative_ttl_seconds <= 0:
        logging.getLogger(__name__).warning(
            "invalid CINEPLEXX_CACHE_NEGATIVE_TTL_SECONDS=%s, using default=3600",
            os.getenv("CINEPLEXX_CACHE_NEGATIVE_TTL_SECONDS", ""),
        )
        cache_negative_ttl_seconds = 3600
    max_film_pages_concurrency = _int("MAX_FILM_PAGES_CONCURRENCY", 4)
    if max_film_pages_concurrency < 1:
        logging.getLogger(__name__).warning(
            "invalid MAX_FILM_PAGES_CONCURRENCY=%s, using default=4",
            os.getenv("MAX_FILM_PAGES_CONCURRENCY", ""),
        )
        max_film_pages_concurrency = 4

    return Config(
        base_url=os.getenv("BASE_URL", "https://cineplexx.me").rstrip("/"),
        location=os.getenv("LOCATION", "0"),
        date_mode=os.getenv("DATE_MODE", "today").strip().lower(),
        fixed_date=os.getenv("FIXED_DATE", "").strip(),
        timezone=os.getenv("TIMEZONE", "Europe/Podgorica"),

        out_dir=out_dir,
        rss_filename=os.getenv("RSS_FILENAME", "cineplexx_rss.xml"),
        events_limit=_int("EVENTS_LIMIT", 150),
        max_events_in_state=max_events_in_state,
        telegram_channels=_list("TELEGRAM_CHANNELS"),
        telegram_post_limit=_int("TELEGRAM_POST_LIMIT", 5),
        redis_url=redis_url,
        cache_enabled=cache_enabled,
        film_cache_ttl_seconds=film_cache_ttl_seconds,
        cache_negative_ttl_seconds=cache_negative_ttl_seconds,
        max_film_pages_concurrency=max_film_pages_concurrency,

        feed_title=os.getenv("FEED_TITLE", "Cineplexx — репертуар"),
        feed_link=os.getenv("FEED_LINK", "https://cineplexx.me"),
        feed_description=os.getenv("FEED_DESCRIPTION", "Текущие фильмы в прокате"),
    )
