from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import aiohttp

from ingest.parsers.base import ParsedDocument, ParsedSection


class URLParser:
    """Parse web URLs by fetching HTML content and extracting text."""

    def can_parse(self, path: Path | str) -> bool:
        """Check if the path is a URL."""
        if isinstance(path, Path):
            return False
        # Simple URL detection
        if isinstance(path, str):
            parsed = urlparse(path)
            return bool(parsed.scheme and parsed.netloc)
        return False

    async def _parse_async_impl(self, url: str) -> ParsedDocument:
        """Fetch and parse a URL asynchronously."""
        from bs4 import BeautifulSoup

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        raise ValueError(f"Failed to fetch URL: HTTP {resp.status}")
                    html_content = await resp.text(encoding="utf-8", errors="replace")
            except aiohttp.ClientError as e:
                raise ValueError(f"Failed to fetch URL: {e}") from e

        soup = BeautifulSoup(html_content, "html.parser")

        # Remove script, style, nav, header, footer elements
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        # Extract title
        title = urlparse(url).netloc
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            title = title_tag.string.strip()
        # Fallback to og:title or h1
        if not title or title == urlparse(url).netloc:
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                title = og_title["content"].strip()
        if not title or title == urlparse(url).netloc:
            h1 = soup.find("h1")
            if h1:
                title = h1.get_text(strip=True)

        # Extract main content
        main_content = soup.find("main") or soup.find("article") or soup.find("body") or soup

        heading_tags = {"h1", "h2", "h3", "h4", "h5", "h6"}
        sections: list[ParsedSection] = []
        current_heading = ""
        current_texts: list[str] = []

        for element in main_content.children if hasattr(main_content, "children") else []:
            if hasattr(element, "name") and element.name in heading_tags:
                # Flush current section
                if current_texts:
                    sections.append(ParsedSection(
                        text="\n".join(current_texts),
                        heading=current_heading,
                    ))
                    current_texts = []
                current_heading = element.get_text(strip=True)
            else:
                text = element.get_text(strip=True) if hasattr(element, "get_text") else str(element).strip()
                if text and len(text) > 10:  # Filter out very short fragments
                    current_texts.append(text)

        if current_texts:
            sections.append(ParsedSection(
                text="\n".join(current_texts),
                heading=current_heading,
            ))

        if not sections:
            # Fallback: just get all text
            all_text = main_content.get_text(separator="\n", strip=True)
            if all_text:
                sections.append(ParsedSection(text=all_text, heading=""))

        if not sections:
            raise ValueError("No content extracted from URL")

        return ParsedDocument(
            title=title,
            source_path=url,
            sections=sections,
            metadata={"url": url, "source_type": "url"},
        )

    def parse(self, url: str) -> ParsedDocument:
        """Synchronous wrapper for async parsing (for compatibility with existing interface)."""
        import asyncio

        # Try to get existing event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running, we need to use a different approach
                # This shouldn't happen in the ingestion pipeline, but handle it
                raise RuntimeError("Cannot parse URL synchronously in running event loop. Use parse_async() instead.")
        except RuntimeError:
            # No event loop, create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self._parse_async_impl(url))
            finally:
                loop.close()

        # Event loop exists but not running
        return loop.run_until_complete(self._parse_async_impl(url))
