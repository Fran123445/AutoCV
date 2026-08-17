from pathlib import Path

import re
import subprocess

from etl.projects.config import (
    CI_WORKFLOW_DIR,
    CONFIG_SIGNAL_NAMES,
    IMPORT_PATTERNS,
    IMPORT_SELF_REFERENCES,
    IMPORT_VENDOR_PREFIXES,
    IMPORT_VENDOR_SEGMENTS,
    MANIFEST_GLOBS,
    MANIFEST_NAMES,
    MAX_IMPORT_SCAN_FILES,
    MIN_SOURCE_FILES,
    README_MAX_CHARS,
    SOURCE_EXTENSIONS,
)


# Compiled once at import: the same handful of patterns runs over every file of
# every project, so recompiling per file would dominate the scan.
_COMPILED_IMPORT_PATTERNS = {
    extension: tuple(re.compile(pattern, re.MULTILINE) for pattern in patterns)
    for extension, patterns in IMPORT_PATTERNS.items()
}


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


def _is_root_file(rel_path: str) -> bool:
    """
    Report whether a repo-relative path sits at the project root.

    Args:
        rel_path (str): A posix path relative to the project root.

    Returns:
        bool: True when the path has no directory component.
    """
    return "/" not in rel_path


def _find_manifests(files: list[str]) -> list[str]:
    """
    Pick the root-level manifest filenames out of a tracked file list.

    Root only: a manifest nested deep is usually a dependency's own, not the
    project's declaration of its stack.

    Args:
        files (list[str]): Tracked file paths relative to the project root.

    Returns:
        list[str]: Manifest filenames found at the root.
    """
    found = []
    for path in files:
        if not _is_root_file(path):
            continue
        if path in MANIFEST_NAMES or any(Path(path).match(g) for g in MANIFEST_GLOBS):
            found.append(path)

    return found


def _count_source_files(files: list[str]) -> int:
    """
    Count tracked files carrying a recognized source extension.

    Args:
        files (list[str]): Tracked file paths relative to the project root.

    Returns:
        int: Number of source files.
    """
    return sum(1 for f in files if Path(f).suffix.lower() in SOURCE_EXTENSIONS)


def _filter_irrelevant_projects(parent_projects: Path) -> list[Path]:
    """
    Keep the child directories worth handing to the model.

    Two cheap, deterministic gates only. Git presence, then a junk floor: a
    manifest or a handful of source files. Anything subtler (an unclear repo
    that clears the floor but may still be throwaway) is left for the transform
    stage to judge, since that is a call code should not make.

    Args:
        parent_projects (Path): Folder whose immediate subdirectories are the
            candidate projects.

    Returns:
        list[Path]: The surviving project directories.
    """
    kept = []
    for child in sorted(parent_projects.iterdir()):
        if not child.is_dir() or not (child / ".git").is_dir():
            continue

        files = _tracked_files(child)
        if _find_manifests(files) or _count_source_files(files) >= MIN_SOURCE_FILES:
            kept.append(child)

    return kept


def _read_manifests(project: Path, manifest_names: list[str]) -> dict[str, str]:
    """
    Read the raw text of each named manifest at a project's root.

    Raw, not parsed: the dead-dep grep and the tech pass both want the original
    text, and each ecosystem's format is the pass's problem, not extract's.

    Args:
        project (Path): The project directory.
        manifest_names (list[str]): Root manifest filenames to read.

    Returns:
        dict[str, str]: Filename to contents for each manifest.
    """
    return {
        name: (project / name).read_text(encoding="utf-8", errors="replace")
        for name in manifest_names
    }


def _find_config_signals(files: list[str]) -> list[str]:
    """
    List the infra/CI marker paths a project carries.

    Args:
        files (list[str]): Tracked file paths relative to the project root.

    Returns:
        list[str]: Marker paths found (root markers plus a CI-dir flag).
    """
    file_set = set(files)
    signals = [name for name in CONFIG_SIGNAL_NAMES if name in file_set]

    if any(f.startswith(CI_WORKFLOW_DIR + "/") for f in files):
        signals.append(CI_WORKFLOW_DIR)

    return signals


def _read_readme(project: Path, files: list[str]) -> str | None:
    """
    Return the text of the project's root README, capped, if one is tracked.

    Args:
        project (Path): The project directory.
        files (list[str]): Tracked file paths relative to the project root.

    Returns:
        str | None: README text truncated to the cap, or None if absent.
    """
    for path in files:
        if _is_root_file(path) and Path(path).stem.lower() == "readme":
            return (project / path).read_text(encoding="utf-8", errors="replace")[
                :README_MAX_CHARS
            ]

    return None


def _extension_histogram(files: list[str]) -> dict[str, int]:
    """
    Count tracked files by lowercased extension.

    Args:
        files (list[str]): Tracked file paths relative to the project root.

    Returns:
        dict[str, int]: Extension to file count, extensionless files omitted.
    """
    histogram: dict[str, int] = {}
    for path in files:
        suffix = Path(path).suffix.lower()
        if suffix:
            histogram[suffix] = histogram.get(suffix, 0) + 1

    return histogram


def _normalize_module(raw: str) -> str | None:
    """
    Reduce a captured import target to the package it names.

    An import path carries more than the package: "os.path", "react-dom/client"
    and "std::collections" all name something inside a package rather than a
    second package. Only the head is kept, except under a registrar prefix,
    where the head is "com" or "github.com" and says nothing on its own.

    Args:
        raw (str): The module as captured from the source.

    Returns:
        str | None: The package name, or None when the import is relative.
    """
    module = raw.strip().strip("\"'")
    # A relative import points back into the project, never at a dependency.
    if not module or module.startswith((".", "/")):
        return None

    # An npm scope is half of the package name: "@scope/name" is the package,
    # anything past it is a path inside that package.
    if module.startswith("@"):
        return "/".join(module.split("/")[:2])

    for separator in ("/", "::", "\\", "."):
        if separator in module:
            parts = [part for part in module.split(separator) if part]
            break
    else:
        parts, separator = [module], ""

    if not parts:
        return None

    if parts[0] in IMPORT_VENDOR_PREFIXES:
        return separator.join(parts[:IMPORT_VENDOR_SEGMENTS])

    return parts[0]


def _local_module_names(files: list[str]) -> set[str]:
    """
    Collect the names a project's own top-level modules would import as.

    Language-agnostic, which is why it survives while a standard library filter
    is not worth having: a repo with a models/ package would otherwise report
    importing "models" as though it were a dependency.

    Args:
        files (list[str]): Tracked file paths relative to the project root.

    Returns:
        set[str]: Top-level directory names and root file stems.
    """
    names = set(IMPORT_SELF_REFERENCES)
    for path in files:
        head, _, tail = path.partition("/")
        names.add(head if tail else Path(head).stem)

    return names


def _scan_imports(project: Path, files: list[str]) -> dict[str, int]:
    """
    Count how many files import each third-party package.

    Manifests say what a project declares; this says what it actually uses, and
    it is the only tech signal a repo without a manifest carries at all. The
    files behind each package are kept, not just how many, since the sampler
    needs to know which files put a given package to use.

    Args:
        project (Path): The project directory.
        files (list[str]): Tracked file paths relative to the project root.

    Returns:
        dict[str, list[str]]: Package name to the files importing it.
    """
    scannable = sorted(
        (f for f in files if Path(f).suffix.lower() in _COMPILED_IMPORT_PATTERNS),
        key=lambda path: (path.count("/"), path),
    )
    local = _local_module_names(files)

    importers: dict[str, list[str]] = {}
    for rel_path in scannable[:MAX_IMPORT_SCAN_FILES]:
        try:
            text = (project / rel_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # A set per file rather than a running tally: a package imported twenty
        # times by one module is one file's worth of evidence, not twenty.
        in_file = set()
        for pattern in _COMPILED_IMPORT_PATTERNS[Path(rel_path).suffix.lower()]:
            for match in pattern.findall(text):
                module = _normalize_module(match)
                if module and module not in local:
                    in_file.add(module)

        for module in in_file:
            importers.setdefault(module, []).append(rel_path)

    return importers


def _gather_signals(projects: list[Path]) -> list[dict]:
    """
    Build the per-project signal dict that the transform stage consumes.

    Everything cheap and deterministic: raw manifests, infra/CI markers, an
    extension histogram, the imported packages, the README, and the tracked file
    tree. Source files are opened only to match import lines, never read for
    meaning; that is the sampling pass's job.

    Args:
        projects (list[Path]): The whitelisted project directories.

    Returns:
        list[dict]: One signal dict per project. See extract() for the shape.
    """
    gathered = []
    for project in projects:
        files = _tracked_files(project)
        gathered.append(
            {
                "path": str(project),
                "name": project.name,
                "manifests": _read_manifests(project, _find_manifests(files)),
                "config_signals": _find_config_signals(files),
                "ext_histogram": _extension_histogram(files),
                "imports": _scan_imports(project, files),
                "readme": _read_readme(project, files),
                "tree": files,
            }
        )

    return gathered


def extract(parent_projects_folder: str) -> list[dict]:
    """
    Extract the signal dicts for every worthwhile project under a parent folder.

    Deterministic, model-free stage: it scans the immediate subdirectories of
    the parent, keeps the git repos that clear the junk floor, and gathers the
    cheap signals the transform stage turns into technologies, concepts and a
    narrative. File lists come from git, so each project's own .gitignore prunes
    the tree.

    Each dict has the shape:
        {
            "path": str,                 # absolute path to the project
            "name": str,                 # directory name
            "manifests": {str: str},     # manifest filename -> raw contents
            "config_signals": [str],     # infra/CI marker paths present
            "ext_histogram": {str: int}, # extension -> tracked file count
            "imports": {str: [str]},     # package -> files importing it
            "readme": str | None,        # capped README text
            "tree": [str],               # tracked file paths, repo-relative
        }

    Args:
        parent_projects_folder (str): Folder whose immediate subdirectories are
            the candidate projects.

    Returns:
        list[dict]: One signal dict per surviving project.
    """
    parent = Path(parent_projects_folder)
    projects = _filter_irrelevant_projects(parent)

    return _gather_signals(projects)
