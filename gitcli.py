from pathlib import Path

import subprocess


def _run(args: list[str], repo: Path) -> str | None:
    """
    Run a git command inside a repo and hand back its stdout.

    Args:
        args (list[str]): The git subcommand and its flags, without "git".
        repo (Path): The repo to run inside.

    Returns:
        str | None: Raw stdout, or None when git errored or is absent.
    """
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotepath=off", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError:
        return None

    if result.returncode != 0:
        return None

    return result.stdout


def tracked_files(repo: Path) -> list[str]:
    """
    The git-tracked files of a repo, as repo-relative posix paths.

    Args:
        repo (Path): The repo directory (already known to be a git repo).

    Returns:
        list[str]: Tracked file paths relative to the repo root, empty on error.
    """
    out = _run(["ls-files", "-z"], repo)
    if out is None:
        return []

    return [path for path in out.split("\0") if path]


def head_commit(repo: Path, short: bool = False) -> str | None:
    """
    The hash of a repo's checked-out commit, or None when git cannot say.

    None when the repo has no commit yet or git errored, which callers using this
    as a cache key read as "never matches", so an unidentifiable repo is handled
    afresh rather than wrongly cached.

    Args:
        repo (Path): The repo directory.
        short (bool): Return git's abbreviated hash instead of the full 40 chars.

    Returns:
        str | None: The HEAD hash, or None.
    """
    args = ["rev-parse", "--short", "HEAD"] if short else ["rev-parse", "HEAD"]

    out = _run(args, repo)
    if out is None:
        return None

    return out.strip() or None


def commit_span(repo: Path) -> tuple[str | None, str | None]:
    """
    The dates of a repo's first and latest commit, as ISO 8601 strings.

    Args:
        repo (Path): The repo directory (already known to be a git repo).

    Returns:
        tuple[str | None, str | None]: The first and latest commit dates.
    """
    out = _run(["log", "--format=%aI"], repo)
    if out is None:
        return None, None

    lines = out.split()
    if not lines:
        return None, None

    return lines[-1], lines[0]
