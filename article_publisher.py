"""Publish an article and its RSS update as one Git commit.

All work happens in a temporary Git worktree. Failed validation, generation,
commit, or push attempts therefore leave the Actions checkout untouched.
Concurrent pushes are detected and retried against the updated branch.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from article_validation import load_articles, validate_article
from generate_feed import article_url, build_feed


class PublicationError(RuntimeError):
    """Raised when an article cannot be safely published."""


def _git(repo: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        if detail:
            print(f"Git {arguments[0]} failed: {detail}", file=sys.stderr)
        raise PublicationError(
            f"Git {arguments[0]} failed. Check branch protection, repository permissions, and the Actions logs."
        )
    return result


def _write_atomic(path: Path, content: bytes) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _write_candidate(worktree: Path, article: dict[str, Any]) -> str:
    news_path = worktree / "news.json"
    articles = load_articles(news_path)
    validate_article(article, existing_ids={existing["id"] for existing in articles})

    updated_articles = [*articles, article]
    feed_bytes = build_feed(updated_articles)
    news_bytes = (json.dumps(updated_articles, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

    # These writes are isolated in a temporary worktree; neither is pushed unless
    # both files stage and commit successfully.
    _write_atomic(news_path, news_bytes)
    _write_atomic(worktree / "feed.xml", feed_bytes)
    return article_url(article["id"])


def publish_article(
    repository: str | Path,
    article: dict[str, Any],
    branch: str,
    *,
    max_attempts: int = 5,
) -> str:
    """Validate, generate, and push one article plus its RSS feed.

    A failed fast-forward push is retried from the newest remote commit. Each
    retry rereads and revalidates the whole database before creating a commit.
    """
    repo = Path(repository).resolve()
    if not repo.is_dir() or max_attempts < 1:
        raise PublicationError("Publishing requires a Git checkout and at least one attempt.")
    if _git(repo, "check-ref-format", "--branch", branch, check=False).returncode != 0:
        raise PublicationError("The configured publishing branch is invalid.")

    validate_article(article)
    remote_ref = f"refs/remotes/origin/{branch}"

    for attempt in range(1, max_attempts + 1):
        _git(repo, "fetch", "origin", f"+refs/heads/{branch}:{remote_ref}")
        base_commit = _git(repo, "rev-parse", "--verify", remote_ref).stdout.strip()

        with tempfile.TemporaryDirectory(prefix="pxl-publish-") as temporary_root:
            worktree = Path(temporary_root) / "checkout"
            _git(repo, "worktree", "add", "--detach", str(worktree), base_commit)
            try:
                article_link = _write_candidate(worktree, article)
                _git(worktree, "config", "user.name", "github-actions[bot]")
                _git(
                    worktree,
                    "config",
                    "user.email",
                    "41898282+github-actions[bot]@users.noreply.github.com",
                )
                _git(worktree, "add", "--", "news.json", "feed.xml")
                _git(worktree, "commit", "-m", f"Publish article {article['id']}")
                candidate_commit = _git(worktree, "rev-parse", "HEAD").stdout.strip()

                push = _git(
                    worktree,
                    "push",
                    "origin",
                    f"HEAD:refs/heads/{branch}",
                    check=False,
                )
                if push.returncode == 0:
                    return article_link

                # The remote may have accepted the commit even if the client
                # lost its connection before receiving the success response.
                _git(repo, "fetch", "origin", f"+refs/heads/{branch}:{remote_ref}")
                latest_commit = _git(repo, "rev-parse", "--verify", remote_ref).stdout.strip()
                if _git(
                    repo,
                    "merge-base",
                    "--is-ancestor",
                    candidate_commit,
                    latest_commit,
                    check=False,
                ).returncode == 0:
                    return article_link

                if latest_commit == base_commit or attempt == max_attempts:
                    detail = (push.stderr or push.stdout).strip()
                    if detail:
                        print(f"Git push failed: {detail}", file=sys.stderr)
                    raise PublicationError("Could not push the article. Check branch protection, repository permissions, and the Actions logs.")
            finally:
                _git(repo, "worktree", "remove", "--force", str(worktree), check=False)

    raise PublicationError("Publishing could not complete after concurrent updates. Please retry.")
