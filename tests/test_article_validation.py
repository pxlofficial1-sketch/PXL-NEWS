import json
import tempfile
import unittest
from pathlib import Path

from article_validation import (
    ArticleValidationError,
    load_articles,
    validate_article,
    validate_articles,
)


def valid_article(**overrides):
    article = {
        "id": "valid-story-1",
        "title": "A valid headline",
        "category": "Technology",
        "description": "A valid description.",
        "date": "2026-11-16",
        "source": "https://example.com/story",
    }
    article.update(overrides)
    return article


class ArticleValidationTests(unittest.TestCase):
    def test_valid_article_and_existing_records(self):
        self.assertEqual(validate_article(valid_article()), valid_article())
        existing = load_articles(Path(__file__).resolve().parents[1] / "news.json")
        self.assertEqual([article["id"] for article in existing], ["welcome", "open-source"])

    def test_duplicate_ids_are_rejected(self):
        with self.assertRaisesRegex(ArticleValidationError, "already in use"):
            validate_articles([valid_article(), valid_article()])

    def test_invalid_ids_are_rejected(self):
        for article_id in ("Bad-ID", "bad_id", "-leading", "trailing-", "a--b"):
            with self.subTest(article_id=article_id):
                with self.assertRaisesRegex(ArticleValidationError, "field 'id'"):
                    validate_article(valid_article(id=article_id))

    def test_missing_fields_are_rejected(self):
        for field in ("id", "title", "category", "description", "date"):
            article = valid_article()
            del article[field]
            with self.subTest(field=field):
                with self.assertRaisesRegex(ArticleValidationError, field):
                    validate_article(article)

    def test_invalid_dates_are_rejected(self):
        for article_date in ("2026/11/16", "2026-02-30", "2026-2-03", "0000-01-01", "not-a-date"):
            with self.subTest(article_date=article_date):
                with self.assertRaisesRegex(ArticleValidationError, "date"):
                    validate_article(valid_article(date=article_date))

    def test_invalid_required_field_values_are_rejected(self):
        for field_values in (
            {"title": "   "},
            {"category": "Unknown"},
            {"description": "x" * 2001},
            {"source": None},
        ):
            with self.subTest(field_values=field_values):
                with self.assertRaises(ArticleValidationError):
                    validate_article(valid_article(**field_values))

    def test_text_length_matches_browser_utf16_limits(self):
        with self.assertRaisesRegex(ArticleValidationError, "title"):
            validate_article(valid_article(title="😀" * 76))

    def test_invalid_source_urls_are_rejected(self):
        for source in (
            "javascript:alert(1)",
            "ftp://example.com/file",
            "https:///missing-host",
            "https://example.com:99999/story",
            "https://user:password@example.com/story",
            "https://:@example.com/story",
            "https://example.com\\@example.org/story",
            "https://example.com/white space",
        ):
            with self.subTest(source=source):
                with self.assertRaisesRegex(ArticleValidationError, "source URL"):
                    validate_article(valid_article(source=source))

    def test_empty_or_missing_source_is_supported(self):
        article = valid_article(source="")
        self.assertEqual(validate_article(article), article)
        article.pop("source")
        self.assertEqual(validate_article(article), article)

    def test_optional_featured_field_must_be_boolean(self):
        with self.assertRaisesRegex(ArticleValidationError, "featured"):
            validate_article(valid_article(featured="yes"))

    def test_malformed_json_and_missing_database_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "news.json"
            database.write_text("[{broken", encoding="utf-8")
            with self.assertRaisesRegex(ArticleValidationError, "malformed JSON"):
                load_articles(database)

            database.write_text(json.dumps({"article": valid_article()}), encoding="utf-8")
            with self.assertRaisesRegex(ArticleValidationError, "JSON array"):
                load_articles(database)


if __name__ == "__main__":
    unittest.main()
