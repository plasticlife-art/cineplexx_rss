import unittest

import cineplexx_rss.telegram as tg


class TelegramFallbacksTests(unittest.TestCase):
    def test_normalize_embed_on_post_url(self) -> None:
        url, is_post = tg._normalize_telegram_url(
            "https://t.me/podgoricanews/20345",
            tg.logging.getLogger("test"),
        )
        self.assertTrue(is_post)
        self.assertIn("embed=1", url)
        self.assertIn("mode=tme", url)

    def test_og_image_fallback_for_post(self) -> None:
        html = """
        <meta property="og:title" content="Post" />
        <meta property="og:image" content="https://cdn4.telesco.pe/file/abc.jpg" />
        <div class="tgme_widget_message text_not_supported_wrap js-widget_message" data-post="podgoricanews/20345">
          <div class="tgme_widget_message_bubble">
            <div class="tgme_widget_message_text js-message_text">Hello</div>
            <time datetime="2026-01-05T10:00:00+00:00"></time>
          </div>
        </div>
        """
        original_fetch = tg._fetch
        try:
            tg._fetch = lambda _: html
            channel = "https://t.me/podgoricanews/20345"
            result = tg.scrape_telegram_channel(channel, limit=1)
        finally:
            tg._fetch = original_fetch

        self.assertEqual(len(result.posts), 1)
        self.assertEqual(result.posts[0].images, ["https://cdn4.telesco.pe/file/abc.jpg"])
