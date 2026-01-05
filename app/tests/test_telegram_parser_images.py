import unittest

from cineplexx_rss.telegram import _TelegramHtmlParser


class TelegramParserImagesTests(unittest.TestCase):
    def test_media_group_images_order(self) -> None:
        html = """
        <div class="tgme_widget_message text_not_supported_wrap js-widget_message" data-post="chan/1">
          <div class="tgme_widget_message_bubble">
            <a class="tgme_widget_message_photo_wrap" style="background-image:url('https://img/1.jpg')">
              <div class="tgme_widget_message_photo" style="background-image:url('https://img/1.jpg')"></div>
            </a>
            <a class="tgme_widget_message_photo_wrap">
              <div class="tgme_widget_message_photo" style="background-image:url('https://img/2.jpg')"></div>
            </a>
            <div class="tgme_widget_message_text js-message_text" dir="auto">Hello</div>
            <time datetime="2026-01-05T10:00:00+00:00"></time>
          </div>
        </div>
        """
        parser = _TelegramHtmlParser("chan")
        parser.feed(html)
        self.assertEqual(len(parser.posts), 1)
        media = parser.posts[0]["media"]
        images = [m["url"] for m in media if m["kind"] == "image"]
        self.assertEqual(images, ["https://img/1.jpg", "https://img/2.jpg"])
