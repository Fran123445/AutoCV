from datetime import datetime
from pathlib import Path

from etl.projects.config import (
    MIN_SOURCE_FILES,
    SOURCE_EXTENSIONS,
    WALK_PRUNE_DIRS,
)
from gitcli import commit_span, head_commit, tracked_files


def _combine_heads(heads: list[str | None]) -> str | None:
    """
    Fold a group's per-repo HEAD hashes into one cache key.

    Sorted and joined, so the key is stable whatever order the repos were walked
    in, and so a multi-repo project turns over whenever any of its repos does. A
    lone repo yields its own hash unchanged. None when no repo has a resolvable
    commit, which the skip reads as "never matches".

    Args:
        heads (list[str | None]): One HEAD hash per repo, None where unresolved.

    Returns:
        str | None: The combined key, or None when nothing was resolvable.
    """
    present = sorted(head for head in heads if head)
    if not present:
        return None

    return "+".join(present)


def _combine_spans(
    spans: list[tuple[str | None, str | None]],
) -> tuple[str | None, str | None]:
    """
    Fold a group's per-repo commit spans into the project's earliest and latest.

    Args:
        spans (list[tuple[str | None, str | None]]): One (first, last) per repo.

    Returns:
        tuple[str | None, str | None]: The project's first and latest dates.
    """
    firsts = [first for first, _ in spans if first]
    lasts = [last for _, last in spans if last]

    first = min(firsts, key=datetime.fromisoformat) if firsts else None
    last = max(lasts, key=datetime.fromisoformat) if lasts else None

    return first, last


def _count_source_files(files: list[str]) -> int:
    """
    Count tracked files carrying a recognized source extension.

    Args:
        files (list[str]): Tracked file paths relative to the project root.

    Returns:
        int: Number of source files.
    """
    return sum(1 for f in files if Path(f).suffix.lower() in SOURCE_EXTENSIONS)


def _discover_repos(parent_projects: Path) -> list[Path]:
    """
    Find every git repo at any depth under the parent folder.

    A repo is a directory holding a .git. The walk descends non-repo folders
    hunting for one and stops at each repo it finds: a repo's own files come
    from git, and a repo nested inside one (a submodule, a vendored checkout) is
    that repo's business, not a separate project of the user's. This is why a
    frontend one level too deep is found where the old immediate-children scan
    missed it. Junk directories are pruned so the walk never crawls a
    node_modules tree for a .git that is not there.

    Args:
        parent_projects (Path): Folder to search beneath.

    Returns:
        list[Path]: Every git repo directory found, parents before children.
    """
    repos = []

    def visit(directory: Path) -> None:
        for child in sorted(directory.iterdir()):
            if not child.is_dir() or child.name in WALK_PRUNE_DIRS:
                continue
            if (child / ".git").is_dir():
                repos.append(child)
            else:
                visit(child)

    visit(parent_projects)
    return repos


def _filter_irrelevant_projects(parent_projects: Path) -> list[Path]:
    """
    Keep the repos worth handing to the model.

    Two cheap, deterministic gates. The repo walk supplies git presence and the
    source-file floor drops empty or scratch repos. Anything subtler (an unclear
    repo that clears the floor but may still be throwaway) is left for the
    transform stage to judge, since that is a call code should not make.

    Args:
        parent_projects (Path): Folder whose repos, at any depth, are the
            candidate projects.

    Returns:
        list[Path]: The surviving project directories.
    """
    kept = []
    for repo in _discover_repos(parent_projects):
        files = tracked_files(repo)
        if _count_source_files(files) >= MIN_SOURCE_FILES:
            kept.append(repo)

    return kept


def _gather_repo_signals(repo: Path) -> dict:
    """
    Build the signal dict for a single git repo.

    The analyzer needs only the repository identity and its tracked file tree.
    Paths are relative to this repo's own root, which is what lets the merge
    below re-root them under an umbrella. "head" is this repo's HEAD hash and
    "span" its (first, latest) commit dates, both of which the merge folds across
    the group.

    Args:
        repo (Path): The repo directory.

    Returns:
        dict: The repo's signal dict, {path, name, tree, head, span}.
    """
    files = tracked_files(repo)

    return {
        "path": str(repo),
        "name": repo.name,
        "tree": files,
        "head": head_commit(repo),
        "span": commit_span(repo),
    }


def _group_repos(parent: Path, repos: list[Path]) -> dict[str, list[Path]]:
    """
    Bucket the kept repos by the top-level folder they sit under.

    A directory the user thinks of as one project can hold several repos (a
    backend and a frontend, for example). On disk that shows up as an umbrella folder
    with no .git of its own whose children are the repos. The top-level segment
    under the parent is that folder's name, so grouping on it collects those
    repos into one project. A repo that is itself a top-level folder is its own
    group of one, which is why single-repo projects come out unchanged.

    Args:
        parent (Path): The scanned parent folder.
        repos (list[Path]): The kept repo directories, at any depth.

    Returns:
        dict[str, list[Path]]: Top-level folder name to the repos beneath it.
    """
    groups: dict[str, list[Path]] = {}
    for repo in repos:
        key = repo.relative_to(parent).parts[0]
        groups.setdefault(key, []).append(repo)

    return groups


def _merge_group(group_root: Path, repos: list[Path]) -> dict:
    """
    Fold a group's repos into one project signal dict.

    A one-repo group is the repo's own signals verbatim: group_root is the repo,
    so nothing is re-rooted. A multi-repo group re-roots every repo's paths under
    the umbrella by prefixing them with the repo's folder, so each path still
    resolves from the group root.

    Args:
        group_root (Path): The umbrella folder (or the repo, for a lone repo).
        repos (list[Path]): The repos in this group.

    Returns:
        dict: The merged project signal dict. See extract() for the shape.
    """
    if len(repos) == 1 and repos[0] == group_root:
        signals = _gather_repo_signals(group_root)
        first_commit_at, last_commit_at = _combine_spans([signals["span"]])
        return {
            "path": signals["path"],
            "name": signals["name"],
            "tree": signals["tree"],
            "head_commit": _combine_heads([signals["head"]]),
            "first_commit_at": first_commit_at,
            "last_commit_at": last_commit_at,
        }

    tree: list[str] = []
    heads: list[str | None] = []
    spans: list[tuple[str | None, str | None]] = []

    for repo in repos:
        rel = repo.relative_to(group_root).as_posix()
        prefix = rel + "/"
        signals = _gather_repo_signals(repo)

        tree.extend(prefix + path for path in signals["tree"])
        heads.append(signals["head"])
        spans.append(signals["span"])

    first_commit_at, last_commit_at = _combine_spans(spans)

    return {
        "path": str(group_root),
        "name": group_root.name,
        "tree": tree,
        "head_commit": _combine_heads(heads),
        "first_commit_at": first_commit_at,
        "last_commit_at": last_commit_at,
    }


def extract(parent_projects_folder: str) -> list[dict]:
    """
    Extract the signal dicts for every worthwhile project under a parent folder.

    Deterministic, model-free stage: it walks the parent for git repos at any
    depth, keeps the ones that clear the junk floor, groups the survivors by the
    top-level folder they live under, and returns the tracked file trees the
    analyzer reads. Grouping is what makes an umbrella folder of several repos
    (a backend, a frontend, a crawler) one project rather than several. File
    lists come from git, so each repo's own .gitignore prunes the tree.

    Each dict has the shape:
        {
            "path": str,                 # absolute path to the project
            "name": str,                 # directory name
            "tree": [str],               # tracked file paths, repo-relative
            "head_commit": str | None,   # combined HEAD hash, the cache key
            "first_commit_at": str | None,  # earliest commit date, ISO 8601
            "last_commit_at": str | None,   # latest commit date, ISO 8601
        }

    In a multi-repo project every tree path is prefixed with its repo folder, so
    it still resolves from "path".

    Args:
        parent_projects_folder (str): Folder whose git repos, at any depth, are
            the candidate projects.

    Returns:
        list[dict]: One signal dict per surviving project.
    """
    parent = Path(parent_projects_folder)
    kept = _filter_irrelevant_projects(parent)
    groups = _group_repos(parent, kept)

    return [
        _merge_group(parent / key, sorted(repos)) for key, repos in sorted(groups.items())
    ]
