import unittest

from cineplexx_rss.cache import cache_key_for_url, NullCache


class CacheTests(unittest.TestCase):
    def test_cache_key_is_stable(self) -> None:
        url = "https://cineplexx.me/film/Test"
        key1 = cache_key_for_url(url)
        key2 = cache_key_for_url(url)
        self.assertEqual(key1, key2)
        self.assertTrue(key1.startswith("cineplexx:film:"))

    def test_null_cache(self) -> None:
        cache = NullCache()
        self.assertIsNone(cache.get_json("x"))
        cache.set_json("x", {"a": 1}, 10)


if __name__ == "__main__":
    unittest.main()
