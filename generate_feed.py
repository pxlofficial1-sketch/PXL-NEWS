
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote
import hashlib

BASE_URL = "https://pxlofficial1-sketch.github.io/PXL-NEWS/"

with open("news.json", "r", encoding="utf-8") as file:
    articles = json.load(file)

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

    article_url = (
        BASE_URL + "article.html?id=" + quote(article["id"])
    )

    title = article["title"]
    description = article["description"]
    category = article.get("category", "Technology")
    date = article.get("date", datetime.now(timezone.utc).date().isoformat())

    article_date = datetime.fromisoformat(date).replace(
        tzinfo=timezone.utc
    )

    guid = hashlib.sha256(
        article["id"].encode("utf-8")
    ).hexdigest()

    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "link").text = article_url
    ET.SubElement(item, "description").text = description
    ET.SubElement(item, "category").text = category
    ET.SubElement(item, "pubDate").text = format_datetime(article_date)
    ET.SubElement(item, "guid", isPermaLink="false").text = guid

    if article.get("source"):
        ET.SubElement(item, "source").text = article["source"]

tree = ET.ElementTree(rss)
ET.indent(tree, space="  ")

xml_data = ET.tostring(rss, encoding="utf-8")

Path("feed.xml").write_bytes(
    b'<?xml version="1.0" encoding="UTF-8"?>\n' + xml_data
)

print(f"Successfully generated RSS feed with {len(articles)} articles!")
