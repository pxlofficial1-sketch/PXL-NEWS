import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from article_validation import ArticleValidationError
from generate_feed import BASE_URL, article_url, build_feed, generate_feed


class FeedGenerationTests(unittest.TestCase):
    def test_existing_article_urls_and_rss_shape_are_preserved(self):
        project = Path(__file__).resolve().parents[1]
        with (project / "news.json").open(encoding="utf-8") as source:
            articles = json.load(source)

        generated_feed = build_feed(articles)
        self.assertEqual(generated_feed, (project / "feed.xml").read_bytes())
        xml_document = ET.fromstring(generated_feed)
        channel = xml_document.find("channel")
        self.assertEqual(xml_document.tag, "rss")
        self.assertEqual(xml_document.attrib["version"], "2.0")
        self.assertEqual(channel.findtext("link"), BASE_URL)
        items = channel.findall("item")
        self.assertEqual(len(items), 2)

        for article, item in zip(articles, items):
            expected = BASE_URL + "article.html?id=" + article["id"]
            self.assertEqual(article_url(article["id"]), expected)
            self.assertEqual(item.findtext("link"), expected)
            self.assertEqual(item.findtext("title"), article["title"])
            self.assertEqual(item.find("guid").attrib["isPermaLink"], "false")

    def test_invalid_database_does_not_modify_existing_feed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            news = root / "news.json"
            feed = root / "feed.xml"
            news.write_text("not-json", encoding="utf-8")
            original_feed = b"existing feed must remain byte-for-byte unchanged"
            feed.write_bytes(original_feed)

            with self.assertRaises(ArticleValidationError):
                generate_feed(news, feed)

            self.assertEqual(feed.read_bytes(), original_feed)

    def test_feed_build_rejects_duplicate_ids(self):
        article = {
            "id": "feed-test",
            "title": "Title",
            "category": "Technology",
            "description": "Description",
            "date": "2026-11-16",
        }
        with self.assertRaisesRegex(ArticleValidationError, "already in use"):
            build_feed([article, article.copy()])


if __name__ == "__main__":
    unittest.main()
