import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

EVENT = json.loads(
    Path(os.environ["GITHUB_EVENT_PATH"]).read_text()
)

issue = EVENT["issue"]
body = issue.get("body") or ""
issue_number = issue["number"]

ALLOWED_CATEGORIES = {
    "AI",
    "Programming",
    "Linux",
    "Gaming",
    "Cybersecurity",
    "Open Source",
    "Technology",
}


def get_field(name):
    pattern = (
        rf"(?ms)^### {re.escape(name)}\s*\n"
        rf"(.*?)(?=^### |\Z)"
    )
    match = re.search(pattern, body)

    if not match:
        return ""

    value = match.group(1).strip()

    if value.lower() in {"_no response_", "no response"}:
        return ""

    return value


headline = get_field("Headline")
category = get_field("Category")
description = get_field("Article description")
source = get_field("Original source URL")

if not headline or not description:
    raise ValueError("Headline and description are required.")

if len(headline) > 150 or len(description) > 2000:
    raise ValueError("Article exceeds the allowed length.")

if category not in ALLOWED_CATEGORIES:
    raise ValueError("Invalid category.")

if source:
    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Invalid source URL.")

article = {
    "id": f"pxl-issue-{issue_number}",
    "title": headline,
    "description": description,
    "category": category,
    "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    "source": source,
}

news_path = Path("news.json")
articles = json.loads(news_path.read_text(encoding="utf-8"))

if any(a["id"] == article["id"] for a in articles):
    raise ValueError("This issue has already been published.")

articles.append(article)

news_path.write_text(
    json.dumps(articles, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)

subprocess.run(
    ["python", "generate_feed.py"],
    check=True,
)

subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
subprocess.run(
    ["git", "config", "user.email",
     "41898282+github-actions[bot]@users.noreply.github.com"],
    check=True,
)

subprocess.run(["git", "add", "news.json", "feed.xml"], check=True)
subprocess.run(
    ["git", "commit", "-m", f"Publish article from issue #{issue_number}"],
    check=True,
)
subprocess.run(["git", "push"], check=True)

print(f"Published: {headline}")
