import asyncio
import logging
import unittest

from cineplexx_rss.cache import cache_key_for_url
from cineplexx_rss.scraper import _build_movie_from_item


class _FakeCache:
    def __init__(self, key: str, value: dict) -> None:
        self._key = key
        self._value = value

    def get_json(self, key: str):
        if key == self._key:
            return self._value
        return None

    def set_json(self, key: str, value: dict, ttl_seconds: int) -> None:
        return None


class ScraperScheduleCacheHitTests(unittest.TestCase):
    def test_schedule_runs_on_description_cache_hit(self) -> None:
        film_url = "https://cineplexx.me/film/Zootropolis-2"
        cache_key = cache_key_for_url(film_url)
        cache = _FakeCache(
            cache_key,
            {
                "title": "Zootropolis 2",
                "description": "Cached description",
                "fetched_at": "2026-01-04T00:00:00Z",
            },
        )
        item = {"title": "Zootropolis 2", "url": film_url}
        fetch_called = {"value": False}

        async def fetch_description(_url: str) -> str:
            fetch_called["value"] = True
            return "Live description"

        async def fetch_sessions_for_date(_url: str, _date: str) -> list[dict]:
            return [
                {
                    "time": "10:00",
                    "hall": "Sala 1",
                    "info": "2D",
                    "session_id": "1",
                    "cinema_name": "CINEPLEXX PODGORICA",
                    "purchase_url": "https://cineplexx.me/buy/1",
                }
            ]

        movie, desc_cache_hit, sessions_count = asyncio.run(
            _build_movie_from_item(
                item=item,
                cache=cache,
                fetch_description=fetch_description,
                fetch_sessions_for_date=fetch_sessions_for_date,
                date_list=["2026-01-05"],
                schedule_enabled=True,
                schedule_max_sessions_per_movie=50,
                schedule_max_dates_per_movie=10,
                film_cache_ttl_seconds=604800,
                cache_negative_ttl_seconds=3600,
                logger=logging.getLogger("test"),
            )
        )

        self.assertTrue(desc_cache_hit)
        self.assertFalse(fetch_called["value"])
        self.assertEqual(movie.description, "Cached description")
        self.assertEqual(len(movie.sessions), 1)
        self.assertEqual(sessions_count, 1)


if __name__ == "__main__":
    unittest.main()
