"""Generate the PXL Tech News RSS feed from the validated article database."""

from __future__ import annotations

import hashlib
import os
import tempfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, time, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote

from article_validation import load_articles, validate_articles


BASE_URL = "https://pxlofficial1-sketch.github.io/PXL-NEWS/"


def article_url(article_id: str) -> str:
    """Build the stable GitHub Pages URL used by RSS and article cards."""
    return BASE_URL + "article.html?id=" + quote(article_id)


def build_feed(articles: list[dict]) -> bytes:
    """Return a complete RSS document without writing or modifying files."""
    validate_articles(articles)

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "PXL Tech News"
    ET.SubElement(channel, "link").text = BASE_URL
    ET.SubElement(channel, "description").text = (
        "Technology, programming, AI and open-source news by PXL Community."
    )
    ET.SubElement(channel, "language").text = "en-us"

    for article in articles:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = article["title"]
        ET.SubElement(item, "link").text = article_url(article["id"])
        ET.SubElement(item, "description").text = article["description"]
        ET.SubElement(item, "category").text = article["category"]

        article_day = date.fromisoformat(article["date"])
        article_datetime = datetime.combine(article_day, time.min, tzinfo=timezone.utc)
        ET.SubElement(item, "pubDate").text = format_datetime(article_datetime)

        guid = hashlib.sha256(article["id"].encode("utf-8")).hexdigest()
        ET.SubElement(item, "guid", isPermaLink="false").text = guid

        if article.get("source"):
            ET.SubElement(item, "source").text = article["source"]

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    xml_data = ET.tostring(rss, encoding="utf-8")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + xml_data


def generate_feed(
    news_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> int:
    """Validate and atomically replace the RSS file; return article count."""
    project_dir = Path(__file__).resolve().parent
    source_path = Path(news_path) if news_path is not None else project_dir / "news.json"
    destination = Path(output_path) if output_path is not None else project_dir / "feed.xml"

    articles = load_articles(source_path)
    feed_bytes = build_feed(articles)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=destination.parent, prefix=f".{destination.name}.", delete=False
        ) as temporary_file:
            temporary_file.write(feed_bytes)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    return len(articles)


def main() -> int:
    count = generate_feed()
    print(f"Successfully generated RSS feed with {count} articles!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
