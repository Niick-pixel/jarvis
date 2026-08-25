"""Auto-commit the memory directory, so "diff history" in BRIEF.md 4.7 is real git history.

Git failing must never fail a request. If the repo cannot be created or the commit does not land,
the Markdown file is still written and still the truth - you just lose the history for that change,
and the reason is reported rather than swallowed.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

AUTHOR_NAME = "jarvis"
AUTHOR_EMAIL = "jarvis@localhost"


def ensure_repo(root: Path) -> bool:
    try:
        from git import Repo
    except ImportError:
        return False
    root.mkdir(parents=True, exist_ok=True)
    try:
        if (root / ".git").is_dir():
            return True
        repo = Repo.init(root)
        with repo.config_writer() as config:
            config.set_value("user", "name", AUTHOR_NAME)
            config.set_value("user", "email", AUTHOR_EMAIL)
        return True
    except Exception as exc:  # noqa: BLE001 - reported, never fatal
        log.warning("memory: could not initialise git repo at %s: %s", root, exc)
        return False


def commit(root: Path, message: str) -> str | None:
    """Stage everything under ./memory/ and commit. Returns the sha, or None if nothing happened."""
    if not ensure_repo(root):
        return None
    try:
        from git import Repo

        repo = Repo(root)
        repo.git.add(A=True)
        if not repo.is_dirty(untracked_files=True):
            return None
        return repo.index.commit(message).hexsha
    except Exception as exc:  # noqa: BLE001
        log.warning("memory: commit failed: %s", exc)
        return None


def history(root: Path, relative: str, limit: int = 20) -> list[dict[str, str]]:
    """Commits that touched one entry, so the Memory page can show how a fact changed."""
    if not (root / ".git").is_dir():
        return []
    try:
        from git import Repo

        repo = Repo(root)
        return [
            {
                "sha": commit.hexsha[:10],
                "message": str(commit.message).strip(),
                "when": commit.committed_datetime.isoformat(),
            }
            for commit in repo.iter_commits(paths=relative, max_count=limit)
        ]
    except Exception as exc:  # noqa: BLE001
        log.warning("memory: history failed for %s: %s", relative, exc)
        return []


def diff(root: Path, relative: str, sha: str) -> str:
    if not (root / ".git").is_dir():
        return ""
    try:
        from git import Repo

        return str(Repo(root).git.show(f"{sha}", "--", relative))
    except Exception as exc:  # noqa: BLE001
        log.warning("memory: diff failed for %s@%s: %s", relative, sha, exc)
        return ""
