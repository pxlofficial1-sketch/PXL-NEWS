"""Turn an authorized GitHub Issue submission into an article publication."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from article_publisher import PublicationError, publish_article  # noqa: E402
from article_validation import ArticleValidationError, validate_article  # noqa: E402


AUTHORIZED_PUBLISHER = "pxlofficial1-sketch"


def get_field(body: str, name: str) -> str:
    pattern = rf"(?ms)^### {re.escape(name)}\s*\n(.*?)(?=^### |\Z)"
    match = re.search(pattern, body)
    if not match:
        return ""

    value = match.group(1).strip()
    if value.lower() in {"_no response_", "no response"}:
        return ""
    return value


def article_from_event(event: dict[str, Any]) -> dict[str, str]:
    issue = event.get("issue")
    if not isinstance(issue, dict):
        raise ArticleValidationError("The GitHub event does not contain an Issue.")

    author = issue.get("user", {}).get("login") if isinstance(issue.get("user"), dict) else None
    if author != AUTHORIZED_PUBLISHER:
        raise ArticleValidationError("Only the authorized publisher account may publish articles.")
    if not str(issue.get("title", "")).startswith("[Publish]"):
        raise ArticleValidationError("The Issue title must start with [Publish].")

    issue_number = issue.get("number")
    if not isinstance(issue_number, int) or isinstance(issue_number, bool) or issue_number < 1:
        raise ArticleValidationError("The Issue number is invalid.")

    body = issue.get("body") or ""
    if not isinstance(body, str):
        raise ArticleValidationError("The Issue form body is invalid.")

    article = {
        "id": f"pxl-issue-{issue_number}",
        "title": get_field(body, "Headline"),
        "category": get_field(body, "Category"),
        "description": get_field(body, "Article description"),
        "date": datetime.now(timezone.utc).date().isoformat(),
        "source": get_field(body, "Original source URL"),
    }
    return validate_article(article)


def _write_outputs(*, article_url: str = "", error: str = "") -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    safe_error = " ".join(error.splitlines()).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    with Path(output_path).open("a", encoding="utf-8") as output_file:
        if article_url:
            output_file.write(f"article_url={article_url}\n")
        if error:
            output_file.write(f"error={safe_error}\n")


def main() -> int:
    try:
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        if not event_path:
            raise ArticleValidationError("GitHub did not provide the Issue event payload.")
        try:
            event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ArticleValidationError("The GitHub Issue event payload is malformed.") from error

        article = article_from_event(event)
        branch = os.environ.get("PUBLISH_BRANCH", "")
        if not branch:
            raise PublicationError("The repository's default publishing branch was not provided.")

        published_url = publish_article(REPOSITORY_ROOT, article, branch)
        _write_outputs(article_url=published_url)
        print(f"Published {article['id']}: {published_url}")
        return 0
    except Exception as error:
        message = str(error) or "An unexpected publication error occurred."
        _write_outputs(error=message)
        print(f"Article publication failed: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
