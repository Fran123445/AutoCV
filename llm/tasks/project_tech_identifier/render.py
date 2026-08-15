"""
Turns an extract signal dict into the prompt block both passes read.

The job side hands the model prose it can read straight through. A repository
has no prose, so the evidence is assembled here instead: what the project
declares (manifests), what it is built out of (extensions), what it ships with
(infra markers) and how it is laid out (tree).
"""

# A tracked tree runs to thousands of paths in a real repo, and the tail of it
# is repetition rather than signal. Shallow paths come first, so the cap keeps
# the layout and drops the leaves.
MAX_TREE_PATHS = 400

# Long enough to carry a stack description, short enough that a book-length
# readme cannot crowd out the manifests below it.
MAX_README_CHARS = 4_000

# Guards against a manifest that pins hundreds of transitive versions.
MAX_MANIFEST_CHARS = 4_000


def _render_manifests(manifests: dict[str, str]) -> str:
    """
    Render each manifest as its own fenced block, contents capped.

    Raw text rather than parsed names: the model reads a pyproject and a pom
    without help, and a parser here would need one branch per ecosystem.

    Args:
        manifests (dict[str, str]): Manifest filename to raw contents.

    Returns:
        str: The rendered blocks, or a marker when the project has none.
    """
    if not manifests:
        return "(none: this project declares no dependency manifest)"

    blocks = []
    for name, content in manifests.items():
        blocks.append(f"--- {name} ---\n{content[:MAX_MANIFEST_CHARS]}")

    return "\n\n".join(blocks)


def _render_histogram(histogram: dict[str, int]) -> str:
    """
    Render the extension counts, most frequent first.

    Args:
        histogram (dict[str, int]): Extension to tracked file count.

    Returns:
        str: Comma-separated "ext xN" entries.
    """
    if not histogram:
        return "(none)"

    ordered = sorted(histogram.items(), key=lambda kv: (-kv[1], kv[0]))

    return ", ".join(f"{ext} x{count}" for ext, count in ordered)


def _render_imports(imports: dict[str, list[str]]) -> str:
    """
    Render the imported packages, most widely used first.

    Counted rather than listed by file: the number separates a dependency the
    project is built on from one touched in a single script, while the file
    names themselves are the sampler's business, not the model's.

    Args:
        imports (dict[str, list[str]]): Package to the files importing it.

    Returns:
        str: Comma-separated "package xN" entries.
    """
    if not imports:
        return "(none found: this project's languages have no import scanner)"

    ordered = sorted(imports.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    return ", ".join(f"{module} x{len(files)}" for module, files in ordered)


def _render_tree(tree: list[str]) -> str:
    """
    Render the tracked file paths, shallowest first, capped.

    Depth ordering is what makes the cap safe: entry points, top-level packages
    and root config survive it, while the deep leaves that get cut are the ones
    that repeat information already carried by the histogram.

    Args:
        tree (list[str]): Tracked file paths relative to the project root.

    Returns:
        str: One path per line, with a note when paths were dropped.
    """
    if not tree:
        return "(none)"

    ordered = sorted(tree, key=lambda path: (path.count("/"), path))
    shown = ordered[:MAX_TREE_PATHS]
    rendered = "\n".join(shown)

    dropped = len(ordered) - len(shown)
    if dropped:
        rendered += f"\n... and {dropped} more files not shown"

    return rendered


def render_signals(signals: dict) -> str:
    """
    Render one project's signal dict as the evidence block for the prompt.

    Args:
        signals (dict): A signal dict as produced by etl.projects.extract.

    Returns:
        str: The evidence block, labelled section by section.
    """
    readme = signals.get("readme")
    config_signals = signals.get("config_signals") or []

    return "\n\n".join(
        [
            f"[project name]\n{signals['name']}",
            f"[readme]\n{readme[:MAX_README_CHARS] if readme else '(none)'}",
            f"[dependency manifests]\n{_render_manifests(signals.get('manifests') or {})}",
            f"[imported packages, with how many files import each]\n{_render_imports(signals.get('imports') or {})}",
            f"[infrastructure and CI files present]\n{', '.join(config_signals) or '(none)'}",
            f"[tracked files by extension]\n{_render_histogram(signals.get('ext_histogram') or {})}",
            f"[tracked file tree]\n{_render_tree(signals.get('tree') or [])}",
        ]
    )
