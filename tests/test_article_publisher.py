import json
import subprocess
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import article_publisher
from article_publisher import PublicationError, publish_article
from article_validation import ArticleValidationError
from generate_feed import BASE_URL, build_feed


def run_git(*args, cwd=None):
    result = subprocess.run(
        ["git", *args], cwd=cwd, check=True, text=True, capture_output=True
    )
    return result.stdout.strip()


def article(article_id, title=None):
    return {
        "id": article_id,
        "title": title or f"Title for {article_id}",
        "category": "Technology",
        "description": f"Description for {article_id}",
        "date": "2026-11-16",
        "source": "",
    }


class GitPublisherTests(unittest.TestCase):
    def make_repositories(self, root, initial_news=None):
        remote = root / "remote.git"
        seed = root / "seed"
        run_git("init", "--bare", "--initial-branch=main", str(remote))
        run_git("init", "--initial-branch=main", str(seed))
        run_git("config", "user.name", "PXL test", cwd=seed)
        run_git("config", "user.email", "pxl-test@example.invalid", cwd=seed)
        run_git("remote", "add", "origin", str(remote), cwd=seed)

        if initial_news is None:
            initial_news = [article("existing-story")]
        if isinstance(initial_news, str):
            news_bytes = initial_news.encode("utf-8")
        else:
            news_bytes = (json.dumps(initial_news, indent=2) + "\n").encode("utf-8")

        (seed / "news.json").write_bytes(news_bytes)
        (seed / "feed.xml").write_bytes(build_feed(initial_news) if isinstance(initial_news, list) else b"old valid feed\n")
        run_git("add", "news.json", "feed.xml", cwd=seed)
        run_git("commit", "-m", "Initial article database", cwd=seed)
        run_git("push", "-u", "origin", "main", cwd=seed)
        return remote, seed

    def clone(self, remote, destination):
        run_git("clone", str(remote), str(destination))
        return destination

    def test_valid_article_publication_updates_database_and_feed_together(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote, seed = self.make_repositories(root)
            checkout = self.clone(remote, root / "checkout")
            original_news = (checkout / "news.json").read_bytes()
            original_feed = (checkout / "feed.xml").read_bytes()

            link = publish_article(checkout, article("pxl-issue-22"), "main")

            self.assertEqual(link, BASE_URL + "article.html?id=pxl-issue-22")
            self.assertEqual((checkout / "news.json").read_bytes(), original_news)
            self.assertEqual((checkout / "feed.xml").read_bytes(), original_feed)
            remote_news = json.loads(run_git("--git-dir", str(remote), "show", "main:news.json"))
            remote_feed = run_git("--git-dir", str(remote), "show", "main:feed.xml")
            self.assertEqual([entry["id"] for entry in remote_news], ["existing-story", "pxl-issue-22"])
            self.assertIn(link, remote_feed)
            self.assertEqual(run_git("--git-dir", str(remote), "diff-tree", "--no-commit-id", "--name-only", "-r", "main").splitlines(), ["feed.xml", "news.json"])

    def test_duplicate_id_is_rejected_without_modifying_local_or_remote_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote, _ = self.make_repositories(root)
            checkout = self.clone(remote, root / "checkout")
            original_news = (checkout / "news.json").read_bytes()
            original_feed = (checkout / "feed.xml").read_bytes()
            original_commit = run_git("rev-parse", "main", cwd=checkout)

            with self.assertRaisesRegex(ArticleValidationError, "already in use"):
                publish_article(checkout, article("existing-story"), "main")

            self.assertEqual((checkout / "news.json").read_bytes(), original_news)
            self.assertEqual((checkout / "feed.xml").read_bytes(), original_feed)
            self.assertEqual(run_git("rev-parse", "main", cwd=checkout), original_commit)

    def test_malformed_database_failure_does_not_modify_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote, _ = self.make_repositories(root, initial_news="[{bad json")
            checkout = self.clone(remote, root / "checkout")
            original_news = (checkout / "news.json").read_bytes()
            original_feed = (checkout / "feed.xml").read_bytes()
            remote_commit = run_git("--git-dir", str(remote), "rev-parse", "main")

            with self.assertRaisesRegex(ArticleValidationError, "malformed JSON"):
                publish_article(checkout, article("new-story"), "main")

            self.assertEqual((checkout / "news.json").read_bytes(), original_news)
            self.assertEqual((checkout / "feed.xml").read_bytes(), original_feed)
            self.assertEqual(run_git("--git-dir", str(remote), "rev-parse", "main"), remote_commit)

    def test_rejected_push_does_not_modify_existing_files_or_remote(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote, _ = self.make_repositories(root)
            checkout = self.clone(remote, root / "checkout")
            original_news = (checkout / "news.json").read_bytes()
            original_feed = (checkout / "feed.xml").read_bytes()
            remote_commit = run_git("--git-dir", str(remote), "rev-parse", "main")
            hook = remote / "hooks" / "pre-receive"
            hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            hook.chmod(0o755)

            with self.assertRaisesRegex(PublicationError, "Could not push"):
                publish_article(checkout, article("blocked-story"), "main", max_attempts=2)

            self.assertEqual((checkout / "news.json").read_bytes(), original_news)
            self.assertEqual((checkout / "feed.xml").read_bytes(), original_feed)
            self.assertEqual(run_git("--git-dir", str(remote), "rev-parse", "main"), remote_commit)

    def test_concurrent_publications_are_retried_and_both_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote, _ = self.make_repositories(root)
            first_checkout = self.clone(remote, root / "checkout-one")
            second_checkout = self.clone(remote, root / "checkout-two")
            start_together = threading.Barrier(2)
            push_barrier = threading.Barrier(2)
            push_count = 0
            push_count_lock = threading.Lock()
            original_git = article_publisher._git

            def synchronized_git(repo, *arguments, **options):
                nonlocal push_count
                if arguments and arguments[0] == "push":
                    with push_count_lock:
                        push_count += 1
                        current_push = push_count
                    if current_push <= 2:
                        push_barrier.wait(timeout=10)
                return original_git(repo, *arguments, **options)

            def publish(checkout, article_id):
                start_together.wait(timeout=10)
                return publish_article(checkout, article(article_id), "main")

            with patch("article_publisher._git", side_effect=synchronized_git):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    first = executor.submit(publish, first_checkout, "concurrent-one")
                    second = executor.submit(publish, second_checkout, "concurrent-two")
                    links = [first.result(timeout=30), second.result(timeout=30)]

            remote_news = json.loads(run_git("--git-dir", str(remote), "show", "main:news.json"))
            ids = {entry["id"] for entry in remote_news}
            self.assertEqual(len(links), 2)
            self.assertGreaterEqual(push_count, 3, "the test should force one concurrent push retry")
            self.assertTrue({"concurrent-one", "concurrent-two"}.issubset(ids))
            feed = run_git("--git-dir", str(remote), "show", "main:feed.xml")
            self.assertTrue(all(link in feed for link in links))


if __name__ == "__main__":
    unittest.main()
