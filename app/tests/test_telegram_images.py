import unittest
from datetime import datetime, timezone

from cineplexx_rss.rss import build_telegram_rss_xml


class TelegramImagesTests(unittest.TestCase):
    def _build(self, images_mode: str, images: list[str]) -> str:
        now = datetime(2026, 1, 4, 12, 0, 0, tzinfo=timezone.utc)
        items = [
            {
                "title": "Post",
                "url": "https://t.me/test/1",
                "description": "Hello",
                "content_text": "Hello",
                "images": images,
                "published": "2026-01-04T12:00:00+00:00",
                "guid": "https://t.me/test/1",
            }
        ]
        return build_telegram_rss_xml(
            title="Test",
            link="https://t.me/test",
            description="Desc",
            now=now,
            items=items,
            images_mode=images_mode,
        )

    def test_no_images(self) -> None:
        rss = self._build("all", [])
        self.assertIn("<content:encoded>", rss)
        self.assertNotIn("<img ", rss)
        self.assertNotIn("<enclosure", rss)

    def test_single_image(self) -> None:
        rss = self._build("all", ["https://example.com/a.jpg"])
        self.assertEqual(rss.count("<img "), 1)
        self.assertIn("a.jpg", rss)

    def test_multiple_images_order(self) -> None:
        rss = self._build(
            "all",
            ["https://example.com/1.jpg", "https://example.com/2.jpg"],
        )
        first = rss.find("1.jpg")
        second = rss.find("2.jpg")
        self.assertTrue(first != -1 and second != -1 and first < second)
        self.assertEqual(rss.count("<img "), 2)

    def test_images_mode_first(self) -> None:
        rss = self._build(
            "first",
            ["https://example.com/1.jpg", "https://example.com/2.jpg"],
        )
        self.assertEqual(rss.count("<img "), 1)
        self.assertIn("1.jpg", rss)
        self.assertNotIn("2.jpg", rss)

    def test_images_mode_none(self) -> None:
        rss = self._build(
            "none",
            ["https://example.com/1.jpg", "https://example.com/2.jpg"],
        )
        self.assertEqual(rss.count("<img "), 0)
