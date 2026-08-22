"""Render tracked repository files as compact evidence for the analyzer."""

from pathlib import Path

import ast
import io
import re
import tokenize


SKIP_EXTENSIONS = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".bmp",
        ".pdf", ".zip", ".gz", ".tar", ".jar", ".class", ".pyc", ".bin",
        ".exe", ".dll", ".so", ".dylib", ".woff", ".woff2", ".ttf", ".eot",
        ".mp4", ".mp3", ".wav", ".mov", ".mdj",
    }
)
SKIP_NAMES = frozenset(
    {
        "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
        "Cargo.lock", "composer.lock", "Gemfile.lock",
    }
)
SKIP_DIRS = frozenset({"seeds", "eval", "test", "tests"})

MAX_FILE_CHARS = 4_000
MAX_TOTAL_CHARS = 600_000


_LINE_COMMENTS = {
    ".js": "//", ".jsx": "//", ".ts": "//", ".tsx": "//", ".mjs": "//",
    ".c": "//", ".cc": "//", ".cpp": "//", ".h": "//", ".hpp": "//",
    ".java": "//", ".kt": "//", ".cs": "//", ".go": "//", ".rs": "//",
    ".sql": "--", ".toml": "#", ".sh": "#", ".yml": "#", ".yaml": "#",
}
_BLOCK_COMMENTS = {
    ".js": (r"/\*", r"\*/"), ".jsx": (r"/\*", r"\*/"), ".ts": (r"/\*", r"\*/"),
    ".tsx": (r"/\*", r"\*/"), ".mjs": (r"/\*", r"\*/"), ".c": (r"/\*", r"\*/"),
    ".cc": (r"/\*", r"\*/"), ".cpp": (r"/\*", r"\*/"), ".h": (r"/\*", r"\*/"),
    ".hpp": (r"/\*", r"\*/"), ".java": (r"/\*", r"\*/"), ".cs": (r"/\*", r"\*/"),
    ".go": (r"/\*", r"\*/"), ".css": (r"/\*", r"\*/"), ".sql": (r"/\*", r"\*/"),
    ".html": (r"<!--", r"-->"), ".htm": (r"<!--", r"-->"), ".vue": (r"<!--", r"-->")
}


def _collapse_blanks(text: str) -> str:
    """Squeeze the blank-line runs that stripping leaves behind."""
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", text)


def _strip_python_docstrings(text: str) -> str:
    """Drop module, class and function docstrings using AST spans."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text

    line_starts = [0]
    for line in text.splitlines(keepends=True):
        line_starts.append(line_starts[-1] + len(line))

    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node, clean=False) is None:
                continue
            doc = node.body[0]
            spans.append(
                (
                    line_starts[doc.lineno - 1] + doc.col_offset,
                    line_starts[doc.end_lineno - 1] + doc.end_col_offset,
                )
            )

    for start, end in sorted(spans, reverse=True):
        text = text[:start] + text[end:]

    return text


def _strip_python_comments(text: str) -> str:
    """Drop Python docstrings and comments without touching # in strings."""
    text = _strip_python_docstrings(text)
    try:
        tokens = [
            tok for tok in tokenize.generate_tokens(io.StringIO(text).readline)
            if tok.type != tokenize.COMMENT
        ]
        return tokenize.untokenize(tokens)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return text


def _strip_comments(text: str, extension: str) -> str:
    """Remove comments for the file's language while keeping executable text."""
    if extension == ".py":
        stripped = _strip_python_comments(text)
    else:
        stripped = text
        if extension in _BLOCK_COMMENTS:
            opener, closer = _BLOCK_COMMENTS[extension]
            stripped = re.sub(f"{opener}.*?{closer}", "", stripped, flags=re.DOTALL)
        if extension in _LINE_COMMENTS:
            marker = re.escape(_LINE_COMMENTS[extension])
            stripped = re.sub(f"{marker}.*", "", stripped)

    return _collapse_blanks(stripped)


def _render_tree(tree: list[str]) -> str:
    """Render tracked paths shallowest first."""
    return "\n".join(sorted(tree, key=lambda p: (p.count("/"), p)))


def _render_files(project_root: Path, tree: list[str]) -> str:
    """Render readable tracked files, applying skip, truncation and cap rules."""
    blocks = []
    total = 0
    for rel_path in sorted(tree, key=lambda p: (p.count("/"), p)):
        name = Path(rel_path).name
        if name in SKIP_NAMES or Path(rel_path).suffix.lower() in SKIP_EXTENSIONS:
            continue
        if rel_path.split("/")[0] in SKIP_DIRS:
            continue

        try:
            text = (project_root / rel_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        text = _strip_comments(text, Path(rel_path).suffix.lower())
        if len(text) > MAX_FILE_CHARS:
            text = text[:MAX_FILE_CHARS] + "\n... (file truncated)"

        block = f"--- {rel_path} ---\n{text}"
        if total + len(block) > MAX_TOTAL_CHARS:
            blocks.append("... (remaining files dropped: dump size cap reached)")
            break

        blocks.append(block)
        total += len(block)

    return "\n\n".join(blocks) if blocks else "(no readable files)"
