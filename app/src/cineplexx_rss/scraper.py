import asyncio
import logging
import re
from datetime import datetime
from time import perf_counter
from typing import List
from playwright.async_api import async_playwright
from .models import Movie
from .cache import cache_key_for_url, Cache

def _normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

async def _cache_get(cache: Cache, key: str) -> dict | None:
    try:
        return await asyncio.to_thread(cache.get_json, key)
    except Exception:
        logging.getLogger(__name__).warning("cache_get_failed key=%s", key, exc_info=True)
        return None


async def _cache_set(cache: Cache, key: str, value: dict, ttl_seconds: int) -> None:
    try:
        await asyncio.to_thread(cache.set_json, key, value, ttl_seconds)
    except Exception:
        logging.getLogger(__name__).warning("cache_set_failed key=%s", key, exc_info=True)


async def scrape_movies(
    base_url: str,
    location: str,
    date_str: str,
    cache: Cache,
    film_cache_ttl_seconds: int,
    cache_negative_ttl_seconds: int,
    max_film_pages_concurrency: int,
) -> List[Movie]:
    url = f"{base_url}/cinemas?location={location}&date={date_str}"
    logger = logging.getLogger(__name__)
    logger.info("cineplexx_scrape_start url=%s location=%s date=%s", url, location, date_str)
    start_ts = perf_counter()
    cache_hits = 0
    cache_misses = 0
    film_pages_fetched = 0
    semaphore = asyncio.Semaphore(max_film_pages_concurrency)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 cineplexx-rss",
            locale="en-US",
        )
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # SPA: wait until film links appear
        await page.wait_for_selector('a[href*="/film/"]', timeout=30000)

        raw = await page.evaluate("""() => {
            const anchors = Array.from(document.querySelectorAll('a[href*="/film/"]'));
            const seen = new Map();
            for (const a of anchors) {
              const href = a.getAttribute('href') || '';
              if (!href.includes('/film/')) continue;

              const textCandidates = [
                a.innerText,
                a.getAttribute('aria-label'),
                a.getAttribute('title'),
                a.querySelector('[data-title]')?.getAttribute('data-title'),
                a.querySelector('.movie-title,.movie__title,.film-title,.film__title')?.innerText,
                a.querySelector('img')?.getAttribute('alt'),
                a.querySelector('img')?.getAttribute('title'),
              ];

              let t = '';
              for (const c of textCandidates) {
                if (!c) continue;
                const s = String(c).trim();
                if (s.length >= 2) { t = s; break; }
              }

              if (!t || t.length < 2) continue;

              const u = href.startsWith('http') ? href : (location.origin + href);
              if (!seen.has(u)) seen.set(u, { title: t, url: u });
            }
            return Array.from(seen.values());
        }""")

        await page.close()

        async def fetch_description(film_url: str) -> str:
            nonlocal film_pages_fetched
            async with semaphore:
                film_pages_fetched += 1
                film_page = await context.new_page()
                desc = ""
                try:
                    await film_page.goto(film_url, wait_until="networkidle", timeout=60000)
                    # Dismiss cookie overlay if present; it blocks clicks.
                    try:
                        await film_page.evaluate("""() => {
                            const ids = ["CybotCookiebotDialog", "CybotCookiebotDialogBodyUnderlay"];
                            for (const id of ids) {
                                const el = document.getElementById(id);
                                if (el) el.remove();
                            }
                            document.body.style.overflow = "auto";
                        }""")
                    except Exception:
                        pass
                    # Prefer specific movie description paragraphs on film pages.
                    await film_page.wait_for_selector(".b-movie-description__text, .b-movie-description", timeout=8000)
                    # Expand if the description is collapsed.
                    try:
                        btn = film_page.locator(".b-movie-description__btn")
                        if await btn.count():
                            try:
                                await film_page.evaluate("""() => {
                                    const ids = ["CybotCookiebotDialog", "CybotCookiebotDialogBodyUnderlay"];
                                    for (const id of ids) {
                                        const el = document.getElementById(id);
                                        if (el) el.remove();
                                    }
                                    document.body.style.overflow = "auto";
                                }""")
                            except Exception:
                                pass
                            await btn.first.click()
                            await film_page.wait_for_timeout(500)
                    except Exception:
                        pass
                    for _ in range(3):
                        desc = await film_page.eval_on_selector_all(
                            ".b-movie-description__text",
                            "els => els.map(e => (e.innerText || '').trim()).filter(Boolean).join('\\n\\n')",
                        )
                        if desc:
                            break
                        desc = await film_page.eval_on_selector(
                            ".b-movie-description",
                            "el => el.innerText || ''",
                        )
                        if desc:
                            break
                        await film_page.wait_for_timeout(1000)
                except Exception:
                    desc = ""
                finally:
                    await film_page.close()
                return _normalize_space(desc)

        async def build_movie(item: dict) -> Movie:
            nonlocal cache_hits, cache_misses
            title = _normalize_space(item.get("title", ""))
            film_url = item.get("url", "")
            if not film_url:
                return Movie(title=title, url="", description="")

            cache_key = cache_key_for_url(film_url)
            cached = await _cache_get(cache, cache_key)
            if cached:
                desc = cached.get("description") or ""
                cached_title = cached.get("title") or title
                if desc or cached.get("error"):
                    cache_hits += 1
                    return Movie(title=cached_title or title, url=film_url, description=desc or "")

            cache_misses += 1
            desc = await fetch_description(film_url)
            if desc:
                await _cache_set(
                    cache,
                    cache_key,
                    {
                        "title": title,
                        "description": desc,
                        "fetched_at": datetime.utcnow().isoformat() + "Z",
                        "source": "cineplexx",
                    },
                    film_cache_ttl_seconds,
                )
            else:
                logger.warning("movie_description_missing url=%s", film_url)
                await _cache_set(
                    cache,
                    cache_key,
                    {
                        "title": title,
                        "description": None,
                        "error": "not_found",
                        "fetched_at": datetime.utcnow().isoformat() + "Z",
                        "source": "cineplexx",
                    },
                    cache_negative_ttl_seconds,
                )
            return Movie(title=title, url=film_url, description=desc)

        tasks = [build_movie(item) for item in raw]
        movies = await asyncio.gather(*tasks)

        await browser.close()

    movies = [m for m in movies if m.title and m.url]
    movies.sort(key=lambda m: (m.title.lower(), m.url))
    duration_ms = int((perf_counter() - start_ts) * 1000)
    logger.info(
        "cineplexx_scrape_done duration_ms=%s movies_found=%s cache_hits=%s cache_misses=%s film_pages_fetched=%s",
        duration_ms,
        len(movies),
        cache_hits,
        cache_misses,
        film_pages_fetched,
    )
    return movies
