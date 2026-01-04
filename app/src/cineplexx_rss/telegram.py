from __future__ import annotations

from dataclasses import dataclass
import logging
from html.parser import HTMLParser
from typing import List, Optional, Dict
from urllib.request import Request, urlopen
from urllib.parse import urljoin
from urllib.parse import urlparse

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_VIDEO_EXTS = {".mp4", ".mov", ".webm", ".m4v", ".avi"}


@dataclass(frozen=True)
class TelegramPost:
    post_id: str
    url: str
    published: str
    title: str
    description: str
    images: List[str]


@dataclass(frozen=True)
class TelegramChannel:
    title: str
    description: str
    posts: List[TelegramPost]


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _normalize_text(text: str) -> str:
    # Preserve paragraph breaks while collapsing extra spaces per line.
    lines = [line.strip() for line in text.replace("\r", "").split("\n")]
    lines = [" ".join(line.split()) for line in lines]
    return "\n".join([line for line in lines if line != ""])


class _TelegramHtmlParser(HTMLParser):
    def __init__(self, channel: str) -> None:
        super().__init__()
        self.channel = channel
        self.title: Optional[str] = None
        self.description: Optional[str] = None
        self.posts: List[Dict[str, object]] = []

        self._in_message = False
        self._message_depth = 0
        self._in_text = False
        self._text_div_depth = 0
        self._current: Optional[Dict[str, object]] = None
        self._pending_media: Optional[Dict[str, str]] = None

    @staticmethod
    def _extract_bg_image(style: str) -> str:
        if "background-image" not in style:
            return ""
        start = style.find("url(")
        if start == -1:
            return ""
        raw = style[start + 4:].strip()
        if raw.startswith(("'", '"')):
            raw = raw[1:]
        end = raw.find(")")
        if end != -1:
            raw = raw[:end]
        raw = raw.strip().strip("'\"")
        return raw

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "") or ""
        cls_tokens = cls.split()
        style = attrs_dict.get("style", "") or ""

        if tag == "meta":
            prop = attrs_dict.get("property")
            content = attrs_dict.get("content") or ""
            if prop == "og:title" and content:
                self.title = content
            elif prop == "og:description" and content:
                self.description = content

        if tag == "div" and "tgme_widget_message" in cls_tokens:
            self._in_message = True
            self._message_depth = 1
            self._current = {
                "post_id": attrs_dict.get("data-post"),
                "published": None,
                "text_parts": [],
                "links": [],
                "media": [],
            }
            return

        if self._in_message and tag == "div":
            self._message_depth += 1
            if "js-message_text" in cls_tokens:
                self._in_text = True
                self._text_div_depth = 1

        if self._in_text and tag == "div":
            self._text_div_depth += 1

        if self._in_text and tag == "br":
            if self._current is not None:
                self._current["text_parts"].append("\n")

        if self._in_message and tag == "time":
            dt = attrs_dict.get("datetime")
            if dt and self._current is not None:
                self._current["published"] = dt

        if self._in_message and tag == "a":
            href = attrs_dict.get("href")
            if not href or self._current is None:
                return
            if "tgme_widget_message_photo_wrap" in cls or "tgme_widget_message_video_player" in cls:
                self._current["media"].append({"url": href, "kind": "media"})
                return
            if "tgme_widget_message_link_preview" in cls:
                self._current["media"].append({"url": href, "kind": "link"})
                return
            if self._in_text:
                self._current["links"].append(href)

        if self._in_message and tag == "a" and "tgme_widget_message_photo_wrap" in cls:
            img_url = self._extract_bg_image(style)
            if img_url and self._current is not None:
                self._current["media"].append({"url": img_url, "kind": "image"})

        if self._in_message and tag == "i" and "tgme_widget_message_video_thumb" in cls:
            img_url = self._extract_bg_image(style)
            if img_url and self._current is not None:
                self._current["media"].append({"url": img_url, "kind": "image"})

        if self._in_message and tag == "video":
            src = attrs_dict.get("src") or ""
            if src and self._current is not None:
                self._current["media"].append({"url": src, "kind": "video"})

    def handle_endtag(self, tag: str) -> None:
        if self._in_text and tag == "div":
            self._text_div_depth -= 1
            if self._text_div_depth <= 0:
                self._in_text = False
                self._text_div_depth = 0

        if self._in_message and tag == "div":
            self._message_depth -= 1
            if self._message_depth <= 0:
                self._in_message = False
                self._message_depth = 0
                if self._current is not None:
                    self.posts.append(self._current)
                self._current = None

    def handle_data(self, data: str) -> None:
        if self._in_text and self._current is not None:
            self._current["text_parts"].append(data)


def _fetch(url: str) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 cineplexx-rss"})
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def scrape_telegram_channel(channel: str, limit: int) -> TelegramChannel:
    logger = logging.getLogger(__name__)
    base = f"https://t.me/s/{channel}"
    html = _fetch(base)
    parser = _TelegramHtmlParser(channel)
    parser.feed(html)

    title = parser.title or f"Telegram: {channel}"
    description = parser.description or ""

    posts: List[TelegramPost] = []
    raw_posts = list(reversed(parser.posts))
    for raw in raw_posts:
        post_id = raw.get("post_id") or ""
        published = raw.get("published") or ""
        if not post_id or not published:
            continue
        text = _normalize_text("".join(raw.get("text_parts") or []))
        links = _dedupe(raw.get("links") or [])
        media_items = raw.get("media") or []
        links = [urljoin("https://t.me/", l) if l.startswith("/") else l for l in links]
        media_items = [
            {
                "url": urljoin("https://t.me/", m.get("url")) if m.get("url", "").startswith("/") else m.get("url"),
                "kind": m.get("kind"),
            }
            for m in media_items
        ]
        links = ["https:" + l if l.startswith("//") else l for l in links]
        media_items = [
            {"url": ("https:" + m["url"]) if m.get("url", "").startswith("//") else m.get("url", ""), "kind": m.get("kind")}
            for m in media_items
        ]
        url = f"https://t.me/{post_id}"

        desc = text
        extra_links = _dedupe([*links, *[m.get("url") for m in media_items if m.get("kind") == "link"]])
        if extra_links:
            desc = (desc + "\n\n" if desc else "") + "\n".join(extra_links)

        image_urls = _dedupe(
            [m.get("url") for m in media_items if m.get("kind") == "image" and m.get("url")]
        )
        if any(m.get("kind") == "image" and not m.get("url") for m in media_items):
            logger.warning("telegram_image_missing_url channel=%s post=%s", channel, post_id)

        file_urls = _dedupe([m.get("url") for m in media_items if m.get("kind") == "video" and m.get("url")])
        media_labels: List[str] = []
        for file_url in file_urls:
            name = urlparse(file_url).path.rsplit("/", 1)[-1]
            label = name or "video"
            media_labels.append(f"file: {label}")

        if not image_urls and not file_urls:
            has_other_media = any(m.get("kind") == "media" for m in media_items)
            if has_other_media:
                media_labels.append("file: media")

        if media_labels:
            desc = (desc + "\n\n" if desc else "") + "\n".join(media_labels)

        title_text = text.strip()
        if not title_text:
            title_text = f"Post {post_id}"
        if len(title_text) > 120:
            title_text = title_text[:117].rstrip() + "..."

        posts.append(
            TelegramPost(
                post_id=post_id,
                url=url,
                published=published,
                title=title_text,
                description=desc.strip(),
                images=image_urls,
            )
        )

        if limit > 0 and len(posts) >= limit:
            break

    return TelegramChannel(title=title, description=description, posts=posts)
