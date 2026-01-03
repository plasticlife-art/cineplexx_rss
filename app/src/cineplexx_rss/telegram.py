from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import List, Optional, Dict
from urllib.request import Request, urlopen
from urllib.parse import urljoin


@dataclass(frozen=True)
class TelegramPost:
    post_id: str
    url: str
    published: str
    title: str
    description: str


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

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "") or ""
        cls_tokens = cls.split()

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
                self._current["media"].append(href)
                return
            if "tgme_widget_message_link_preview" in cls:
                self._current["media"].append(href)
                return
            if self._in_text:
                self._current["links"].append(href)

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
    base = f"https://t.me/s/{channel}"
    html = _fetch(base)
    parser = _TelegramHtmlParser(channel)
    parser.feed(html)

    title = parser.title or f"Telegram: {channel}"
    description = parser.description or ""

    posts: List[TelegramPost] = []
    for raw in parser.posts:
        post_id = raw.get("post_id") or ""
        published = raw.get("published") or ""
        if not post_id or not published:
            continue
        text = _normalize_text("".join(raw.get("text_parts") or []))
        links = _dedupe(raw.get("links") or [])
        media = _dedupe(raw.get("media") or [])
        links = [urljoin("https://t.me/", l) if l.startswith("/") else l for l in links]
        media = [urljoin("https://t.me/", m) if m.startswith("/") else m for m in media]
        links = ["https:" + l if l.startswith("//") else l for l in links]
        media = ["https:" + m if m.startswith("//") else m for m in media]
        url = f"https://t.me/{post_id}"

        desc = text
        extra_links = _dedupe([*links, *media])
        if extra_links:
            desc = (desc + "\n\n" if desc else "") + "\n".join(extra_links)

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
            )
        )

        if limit > 0 and len(posts) >= limit:
            break

    return TelegramChannel(title=title, description=description, posts=posts)
