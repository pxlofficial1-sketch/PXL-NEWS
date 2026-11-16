"""Validation rules shared by article publication and RSS generation."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


ARTICLE_CATEGORIES = frozenset(
    {
        "AI",
        "Programming",
        "Linux",
        "Gaming",
        "Cybersecurity",
        "Open Source",
        "Technology",
        "Community",
    }
)
ARTICLE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_ARTICLE_ID_LENGTH = 80
MAX_TITLE_LENGTH = 150
MAX_DESCRIPTION_LENGTH = 2000


class ArticleValidationError(ValueError):
    """Raised when an article or article database does not match the schema."""


def _javascript_length(value: str) -> int:
    """Match HTML input length limits, which count UTF-16 code units."""
    return len(value.encode("utf-16-le", errors="surrogatepass")) // 2


def _required_text(article: dict[str, Any], field: str, max_length: int | None = None) -> str:
    value = article.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ArticleValidationError(f"Article field '{field}' is required and must be text.")
    if value != value.strip():
        raise ArticleValidationError(f"Article field '{field}' must not have leading or trailing whitespace.")
    if max_length is not None and _javascript_length(value) > max_length:
        raise ArticleValidationError(f"Article field '{field}' must be at most {max_length} characters.")
    return value


def validate_source_url(value: Any) -> str:
    """Validate an optional source URL; an empty string means no source."""
    if not isinstance(value, str):
        raise ArticleValidationError("Article field 'source' must be a URL string or empty.")
    if value == "":
        return value
    if value != value.strip() or "\\" in value or any(
        character.isspace() or ord(character) < 32 for character in value
    ):
        raise ArticleValidationError("Article source URL must not contain whitespace.")

    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        # Accessing .port validates that the supplied port is numeric and in range.
        parsed.port
    except ValueError as error:
        raise ArticleValidationError("Article source URL is invalid.") from error

    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or not hostname:
        raise ArticleValidationError("Article source URL must be an absolute HTTP or HTTPS URL.")
    if parsed.username is not None or parsed.password is not None:
        raise ArticleValidationError("Article source URL must not contain embedded credentials.")
    return value


def validate_article(article: Any, existing_ids: set[str] | None = None) -> dict[str, Any]:
    """Validate one article without mutating it and return the original object."""
    if not isinstance(article, dict):
        raise ArticleValidationError("Each article must be a JSON object.")

    article_id = _required_text(article, "id", MAX_ARTICLE_ID_LENGTH)
    if not ARTICLE_ID_PATTERN.fullmatch(article_id):
        raise ArticleValidationError(
            "Article field 'id' must use lowercase letters and numbers separated by single hyphens."
        )
    if existing_ids is not None and article_id in existing_ids:
        raise ArticleValidationError(f"Article ID '{article_id}' is already in use.")

    _required_text(article, "title", MAX_TITLE_LENGTH)
    category = _required_text(article, "category")
    if category not in ARTICLE_CATEGORIES:
        allowed = ", ".join(sorted(ARTICLE_CATEGORIES))
        raise ArticleValidationError(f"Article category must be one of: {allowed}.")
    _required_text(article, "description", MAX_DESCRIPTION_LENGTH)

    article_date = _required_text(article, "date")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", article_date):
        raise ArticleValidationError("Article field 'date' must use YYYY-MM-DD format.")
    try:
        date.fromisoformat(article_date)
    except ValueError as error:
        raise ArticleValidationError("Article field 'date' must be a real calendar date.") from error

    if "source" in article:
        validate_source_url(article["source"])
    if "featured" in article and not isinstance(article["featured"], bool):
        raise ArticleValidationError("Optional article field 'featured' must be true or false.")

    return article


def validate_articles(articles: Any) -> list[dict[str, Any]]:
    """Validate the complete article list, including ID uniqueness."""
    if not isinstance(articles, list):
        raise ArticleValidationError("The article database must be a JSON array.")

    seen_ids: set[str] = set()
    for index, article in enumerate(articles, start=1):
        try:
            validate_article(article, existing_ids=seen_ids)
        except ArticleValidationError as error:
            raise ArticleValidationError(f"Article {index}: {error}") from error
        seen_ids.add(article["id"])
    return articles


def load_articles(path: str | Path) -> list[dict[str, Any]]:
    """Read and validate an article database, with actionable file errors."""
    source_path = Path(path)
    try:
        with source_path.open("r", encoding="utf-8") as source_file:
            articles = json.load(source_file)
    except json.JSONDecodeError as error:
        raise ArticleValidationError(
            f"{source_path} contains malformed JSON at line {error.lineno}, column {error.colno}."
        ) from error
    except UnicodeDecodeError as error:
        raise ArticleValidationError(f"{source_path} is not valid UTF-8 JSON.") from error
    except OSError as error:
        raise ArticleValidationError(f"Could not read {source_path}: {error.strerror or error}.") from error

    return validate_articles(articles)
