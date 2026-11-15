
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
import hashlib

BASE_URL = "https://pxlofficial1-sketch.github.io/PXL-NEWS/"

# Read articles
with open("news.json", "r", encoding="utf-8") as file:
    articles = json.load(file)

# Create RSS structure
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

    title = article["title"]
    description = article["description"]
    date = article.get("date", datetime.now(timezone.utc).date().isoformat())

    article_date = datetime.fromisoformat(date).replace(
        tzinfo=timezone.utc
    )

    article_id = hashlib.sha256(
        title.encode("utf-8")
    ).hexdigest()

    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "link").text = BASE_URL
    ET.SubElement(item, "description").text = description
    ET.SubElement(item, "pubDate").text = format_datetime(article_date)
    ET.SubElement(item, "guid", isPermaLink="false").text = article_id

# Save RSS feed
tree = ET.ElementTree(rss)
ET.indent(tree, space="  ")
xml_data = ET.tostring(rss, encoding="utf-8")
Path("feed.xml").write_bytes(
    b'<?xml version="1.0" encoding="UTF-8"?>\n' + xml_data
)

print("RSS feed generated successfully!")

