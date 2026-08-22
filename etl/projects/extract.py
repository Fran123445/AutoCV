from pathlib import Path

import subprocess

from etl.projects.config import (
    MIN_SOURCE_FILES,
    SOURCE_EXTENSIONS,
    WALK_PRUNE_DIRS,
)


def _tracked_files(project: Path) -> list[str]:
    """
    List the git-tracked files of a project as repo-relative posix paths.

    Tracked, not walked: git already knows what the user authored, so this drops
    gitignored junk (a scraped data/ dir, node_modules, build output) for free
    and without a .gitignore parser. Untracked-but-new files are missed, which
    is the intended reading of "part of the project".

    -z keeps NUL separators and quotepath=off keeps non-ASCII names literal, so
    paths never arrive quoted or split on embedded characters.

    Args:
        project (Path): The project directory (already known to be a git repo).

    Returns:
        list[str]: Tracked file paths relative to the project root.
    """
    result = subprocess.run(
        ["git", "-c", "core.quotepath=off", "-C", str(project), "ls-files", "-z"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        return []

    return [path for path in result.stdout.split("\0") if path]


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
        files = _tracked_files(repo)
        if _count_source_files(files) >= MIN_SOURCE_FILES:
            kept.append(repo)

    return kept


def _gather_repo_signals(repo: Path) -> dict:
    """
    Build the signal dict for a single git repo.

    The analyzer needs only the repository identity and its tracked file tree.
    Paths are relative to this repo's own root, which is what lets the merge
    below re-root them under an umbrella.

    Args:
        repo (Path): The repo directory.

    Returns:
        dict: The repo's signal dict. See extract() for the shape.
    """
    files = _tracked_files(repo)

    return {
        "path": str(repo),
        "name": repo.name,
        "tree": files,
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
        return _gather_repo_signals(group_root)

    tree: list[str] = []

    for repo in repos:
        rel = repo.relative_to(group_root).as_posix()
        prefix = rel + "/"
        signals = _gather_repo_signals(repo)

        tree.extend(prefix + path for path in signals["tree"])

    return {
        "path": str(group_root),
        "name": group_root.name,
        "tree": tree,
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
