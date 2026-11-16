import importlib.util
import re
import unittest
from pathlib import Path

from article_validation import (
    ARTICLE_CATEGORIES,
    MAX_ARTICLE_ID_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    MAX_TITLE_LENGTH,
)


PROJECT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT / ".github/workflows/.github/scripts/publish_issue.py"
WORKFLOW_PATH = PROJECT / ".github/workflows/publish-news.yml"

spec = importlib.util.spec_from_file_location("publish_issue", SCRIPT_PATH)
publish_issue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish_issue)


class PublishingWorkflowTests(unittest.TestCase):
    def test_workflow_invokes_existing_script_at_correct_path(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        command = re.search(r"run:\s+python\s+([^\s]+)", workflow)
        self.assertIsNotNone(command)
        self.assertEqual(command.group(1), ".github/workflows/.github/scripts/publish_issue.py")
        self.assertTrue((PROJECT / command.group(1)).is_file())

    def test_permissions_are_limited_to_contents_and_issue_feedback(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: none\n  issues: none", workflow)
        self.assertIn("permissions:\n      contents: write\n      issues: write", workflow)
        self.assertNotRegex(workflow, r"(?m)^\s+(pull-requests|actions|packages):\s+write\s*$")
        self.assertIn("github.event.issue.user.login == 'pxlofficial1-sketch'", workflow)
        self.assertIn("if: always()", workflow)
        self.assertIn("gh issue close", workflow)
        self.assertIn("The issue is still open", workflow)

    def test_issue_adapter_keeps_owner_only_gate_and_parses_form(self):
        event = {
            "issue": {
                "number": 22,
                "title": "[Publish] Example",
                "user": {"login": "pxlofficial1-sketch"},
                "body": (
                    "### Headline\nExample title\n\n"
                    "### Category\nCommunity\n\n"
                    "### Article description\nExample body\n\n"
                    "### Original source URL\n_No response_\n"
                ),
            }
        }
        article = publish_issue.article_from_event(event)
        self.assertEqual(article["id"], "pxl-issue-22")
        self.assertEqual(article["category"], "Community")
        self.assertEqual(article["source"], "")

        event["issue"]["user"]["login"] = "another-user"
        with self.assertRaisesRegex(ValueError, "authorized publisher"):
            publish_issue.article_from_event(event)

    def test_publisher_contains_no_credentials_or_secrets(self):
        publisher = (PROJECT / "publisher.html").read_text(encoding="utf-8")
        for forbidden in ("GH_TOKEN", "GITHUB_TOKEN", "github_pat_", "ghp_", "secrets."):
            self.assertNotIn(forbidden, publisher)
        self.assertIn("function validateArticle", publisher)
        self.assertIn("function validateDatabase", publisher)

    def test_browser_and_python_validator_rules_match(self):
        publisher = (PROJECT / "publisher.html").read_text(encoding="utf-8")
        categories_block = re.search(
            r"const allowedCategories = new Set\(\[(.*?)\]\);", publisher, re.DOTALL
        )
        self.assertIsNotNone(categories_block)
        browser_categories = set(re.findall(r'"([^"]+)"', categories_block.group(1)))
        self.assertEqual(browser_categories, ARTICLE_CATEGORIES)
        self.assertIn(f"const maxArticleIdLength = {MAX_ARTICLE_ID_LENGTH};", publisher)
        self.assertIn(f"const maxTitleLength = {MAX_TITLE_LENGTH};", publisher)
        self.assertIn(f"const maxDescriptionLength = {MAX_DESCRIPTION_LENGTH};", publisher)


if __name__ == "__main__":
    unittest.main()
