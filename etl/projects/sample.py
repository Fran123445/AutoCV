"""
Chooses which source files the narrative and descr passes read.

The technology pass never opens a source file: manifests and import lines
already answer "which". Saying how a technology was used, or what the project
actually does, cannot be answered from declarations, and reading every file is
neither affordable nor needed. So the budget goes to the files that carry the
most meaning per byte: the entry points, then whatever puts each identified
technology to work.
"""

from pathlib import Path

import re

from etl.projects.config import (
    ENTRYPOINT_NAMES,
    MAX_FILES_PER_TECHNOLOGY,
    MAX_SAMPLE_BYTES,
    MAX_SAMPLE_FILE_BYTES,
)
from llm.registries.technologies import SURFACE_TO_NAME


_MODULE_SEPARATORS = re.compile(r"[_-]")


def _resolve_module(module: str) -> str | None:
    """
    Find the technology a module name belongs to.

    Exact lookup is not enough, because a package rarely spells its technology
    the way the registry does. "sqlite3" carries a version, and "langchain_core"
    is one package of a family. Both are unmistakable evidence of a technology
    the registry does hold, and matching only exact surfaces silently loses them.

    Prefixes are tried on separator boundaries and longest first, so
    "langchain_openai" can reach langchain without "go" or "c" matching whatever
    they happen to start.

    Args:
        module (str): A package name as scanned from an import.

    Returns:
        str | None: The canonical technology name, or None when nothing matches.
    """
    key = module.casefold()
    if key in SURFACE_TO_NAME:
        return SURFACE_TO_NAME[key]

    # Version suffixes: sqlite3, psycopg2, python3.
    unversioned = key.rstrip("0123456789.")
    if unversioned != key and unversioned in SURFACE_TO_NAME:
        return SURFACE_TO_NAME[unversioned]

    parts = _MODULE_SEPARATORS.split(key)
    for length in range(len(parts) - 1, 0, -1):
        candidate = "_".join(parts[:length])
        if candidate in SURFACE_TO_NAME:
            return SURFACE_TO_NAME[candidate]

    return None


def _entrypoint_files(tree: list[str]) -> list[str]:
    """
    Find the project's entry points, shallowest first.

    Args:
        tree (list[str]): Tracked file paths relative to the project root.

    Returns:
        list[str]: Paths whose file name is a known entry point.
    """
    found = [path for path in tree if Path(path).name in ENTRYPOINT_NAMES]

    return sorted(found, key=lambda path: (path.count("/"), path))


def _files_by_technology(
    technologies: list[str], imports: dict[str, list[str]]
) -> dict[str, list[str]]:
    """
    Map each identified technology to the files importing it.

    Resolution runs from the import outwards: a module is looked up in the
    surface table and kept when it lands on a technology that was identified.
    Technologies with no importing file (a database named only in a manifest, a
    language inferred from an extension) simply get no entry.

    Args:
        technologies (list[str]): Canonical names from the technology pass.
        imports (dict[str, list[str]]): Package to the files importing it.

    Returns:
        dict[str, list[str]]: Technology name to the files that import it.
    """
    wanted = set(technologies)

    carriers: dict[str, list[str]] = {}
    for module, files in imports.items():
        technology = _resolve_module(module)
        if technology in wanted:
            carriers.setdefault(technology, []).extend(files)

    return carriers


def _filler_files(imports: dict[str, list[str]], tree: list[str]) -> list[str]:
    """
    Rank the remaining files by how much of the project they tie together.

    Needed because the technology list can be thin for reasons that say nothing
    about the project: a repo whose main dependency is missing from the registry
    ends up with no carrier files at all, and would otherwise be described from
    its entry point alone. A file importing many distinct packages is where the
    project's parts meet, which makes it the next best thing to read.

    Args:
        imports (dict[str, list[str]]): Package to the files importing it.
        tree (list[str]): Tracked file paths relative to the project root.

    Returns:
        list[str]: Files that import at least one package, busiest first.
    """
    distinct: dict[str, int] = {}
    for files in imports.values():
        for path in files:
            distinct[path] = distinct.get(path, 0) + 1

    return sorted(distinct, key=lambda path: (-distinct[path], path))


def _select_files(
    project: Path, signals: dict, technologies: list[str]
) -> list[str]:
    """
    Pick the files to show, in the order they earn their place.

    Entry points first, since they describe the project rather than a corner of
    it. Then the files behind each technology, largest first: size is a rough
    stand-in for how much of the technology's use lives there. Then whatever
    else ties the most packages together, which keeps a thin technology list
    from starving the sample. Ordering matters because the byte budget is spent
    walking this list.

    Args:
        project (Path): The project directory.
        signals (dict): A signal dict as produced by etl.projects.extract.
        technologies (list[str]): Canonical names from the technology pass.

    Returns:
        list[str]: Paths to read, most informative first, without duplicates.
    """

    def size_of(rel_path: str) -> int:
        try:
            return (project / rel_path).stat().st_size
        except OSError:
            return 0

    imports = signals.get("imports") or {}
    tree = signals.get("tree") or []

    selected = list(_entrypoint_files(tree))

    carriers = _files_by_technology(technologies, imports)
    # Sorted by name so the sample is stable across runs rather than following
    # whatever order the identifier happened to report.
    for technology in sorted(carriers):
        files = sorted(set(carriers[technology]), key=size_of, reverse=True)
        selected.extend(files[:MAX_FILES_PER_TECHNOLOGY])

    selected.extend(_filler_files(imports, tree))

    deduped = []
    for path in selected:
        if path not in deduped:
            deduped.append(path)

    return deduped


def build_sample(project_path: str, signals: dict, technologies: list[str]) -> str:
    """
    Render the sampled source of a project as one block for the prompt.

    Args:
        project_path (str): Path to the project directory.
        signals (dict): A signal dict as produced by etl.projects.extract.
        technologies (list[str]): Canonical names from the technology pass.

    Returns:
        str: The sampled files, each under its own path header.
    """
    project = Path(project_path)

    blocks = []
    budget = MAX_SAMPLE_BYTES
    for rel_path in _select_files(project, signals, technologies):
        if budget <= 0:
            break

        try:
            text = (project / rel_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        allowed = min(MAX_SAMPLE_FILE_BYTES, budget)
        if len(text) > allowed:
            text = text[:allowed] + "\n... (file truncated)"

        # Charged on what the file actually costs, not on what it was allowed to
        # cost: billing every file the per-file cap would spend the whole budget
        # on a handful of small ones.
        budget -= len(text)
        blocks.append(f"--- {rel_path} ---\n{text}")

    if not blocks:
        return "(no source files could be sampled)"

    return "\n\n".join(blocks)
