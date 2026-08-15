# Tunables for the projects extract stage: which files signal a stack, which
# count as source, and where the junk floor sits. Kept out of extract.py so the
# knobs move without touching the walk logic.

# Manifests are the highest-precision tech signal a repo carries: they declare
# the stack instead of implying it. Exact filenames first; the glob covers
# ecosystems that name the file after the project (dotnet).
MANIFEST_NAMES = (
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "package.json",
    "pom.xml",
    "go.mod",
    "Cargo.toml",
    "Gemfile",
    "composer.json",
    "build.gradle",
)
MANIFEST_GLOBS = ("*.csproj",)

# Tech that leaves no manifest row: infra and CI declare themselves by their own
# files, not by a dependency line. Presence is the whole signal, so these are
# reported as found paths rather than parsed.
CONFIG_SIGNAL_NAMES = (
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Makefile",
    ".gitlab-ci.yml",
)
# A directory whose mere existence is a signal: any workflow file under it means
# GitHub Actions, without caring which one.
CI_WORKFLOW_DIR = ".github/workflows"

# Counted for the cull floor and handed to transform as a stack hint (many .rs
# without a Cargo.toml still means Rust). Kept wide on purpose: a repo the model
# should judge is better admitted than dropped over a missing extension.
SOURCE_EXTENSIONS = frozenset(
    {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".rb",
        ".php", ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".kt", ".scala",
        ".swift", ".m", ".sql", ".sh", ".r", ".ipynb", ".vue", ".svelte",
    }
)

# A repo under this many source files and with no manifest is treated as junk
# (scratch, config-only, empty scaffold) and never reaches the model.
MIN_SOURCE_FILES = 3

# README is narrative fuel for the task_desc pass, not a parse target; cap it so
# a monster readme cannot blow up the dict handed downstream.
README_MAX_CHARS = 20_000

# What a project imports, keyed by the extension of the file doing the
# importing. Manifests only cover what a project *declares*, and a repo without
# one is otherwise invisible: nothing but filenames reaches the model. Imports
# cover what it actually *uses*, which is also the stronger claim for a CV.
#
# Keyed by extension rather than applied blindly because the syntax is the one
# thing that really does vary by language. An extension with no pattern is
# simply not scanned, so adding a language here can never worsen the ones
# already handled.
#
# Each pattern captures the module in group 1. They are deliberately loose: a
# false positive costs one line in the prompt and lands in
# discarded_technologies, while a false negative loses a technology outright.
# Standard library modules are kept on purpose. "sqlite3", "json" and "csv" name
# technologies the project genuinely uses, and anything outside the registry is
# unrepresentable to the model anyway, so filtering them would only lose signal.
IMPORT_PATTERNS = {
    ".py": (
        r"^\s*import\s+([\w.]+)",
        r"^\s*from\s+([\w.]+)\s+import",
    ),
    ".js": (
        r"""^\s*import\s+.*?from\s+['"]([^'"]+)['"]""",
        r"""^\s*import\s+['"]([^'"]+)['"]""",
        r"""require\(\s*['"]([^'"]+)['"]\s*\)""",
    ),
    ".ts": (
        r"""^\s*import\s+.*?from\s+['"]([^'"]+)['"]""",
        r"""^\s*import\s+['"]([^'"]+)['"]""",
        r"""require\(\s*['"]([^'"]+)['"]\s*\)""",
    ),
    ".java": (r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;",),
    ".kt": (r"^\s*import\s+([\w.]+)",),
    ".cs": (r"^\s*using\s+(?:static\s+)?([\w.]+)\s*;",),
    ".go": (
        r"""^\s*(?:import\s+)?(?:[\w.]+\s+)?"([\w./-]+)"\s*$""",
    ),
    ".rs": (r"^\s*use\s+([\w:]+)",),
    ".rb": (r"""^\s*require(?:_relative)?\s+['"]([^'"]+)['"]""",),
    ".php": (r"^\s*use\s+([\w\\]+)",),
    ".c": (r"^\s*#\s*include\s*[<\"]([^>\"]+)[>\"]",),
    ".cpp": (r"^\s*#\s*include\s*[<\"]([^>\"]+)[>\"]",),
    ".h": (r"^\s*#\s*include\s*[<\"]([^>\"]+)[>\"]",),
    ".r": (r"^\s*(?:library|require)\(\s*[\"']?([\w.]+)",),
}
# Extensions sharing a syntax, so the table above stays one entry per dialect.
IMPORT_PATTERNS[".jsx"] = IMPORT_PATTERNS[".js"]
IMPORT_PATTERNS[".tsx"] = IMPORT_PATTERNS[".ts"]
IMPORT_PATTERNS[".mjs"] = IMPORT_PATTERNS[".js"]
IMPORT_PATTERNS[".cc"] = IMPORT_PATTERNS[".cpp"]
IMPORT_PATTERNS[".hpp"] = IMPORT_PATTERNS[".cpp"]

# Namespaced imports whose first segment is a registrar rather than the library:
# "com.fasterxml.jackson" and "github.com/gin-gonic/gin" both say nothing until
# the second and third segments. Everything else keeps its first segment only.
IMPORT_VENDOR_PREFIXES = ("com", "org", "net", "io", "github.com", "gitlab.com", "golang.org")
IMPORT_VENDOR_SEGMENTS = 3

# Module-relative keywords that read like a package but name the current crate
# or namespace, so they are dropped the same way a local module is.
IMPORT_SELF_REFERENCES = frozenset({"crate", "self", "super", "__future__"})

# One read per source file, so a monorepo does not turn extract into a crawl.
# Ordered shallowest first before the cap applies, matching the tree.
MAX_IMPORT_SCAN_FILES = 300

# Sampling: which source files the narrative and descr passes actually read.
#
# The tech pass gets by on declarations, since it only answers "which". Saying
# how a technology was used, or what the project does, means reading the code,
# and reading all of it is neither affordable nor necessary.

# Read first whatever the file count. An entry point states the project's shape
# in one file: what it wires together, what it is for, how it is invoked.
ENTRYPOINT_NAMES = (
    "main.py",
    "__main__.py",
    "app.py",
    "cli.py",
    "run.py",
    "server.py",
    "index.js",
    "index.ts",
    "main.go",
    "main.rs",
    "Program.cs",
)

# Whole-sample ceiling. Projects here run 26KB to 177KB of source, so this
# reads a small project entirely and the load-bearing part of a large one.
MAX_SAMPLE_BYTES = 50_000

# Per-file ceiling, so one generated or vendored monster cannot eat the budget
# on its own. Truncation is marked in the rendered sample.
MAX_SAMPLE_FILE_BYTES = 12_000

# Files carrying a given technology. Two is enough to show a pattern of use
# without spending the budget on one dependency.
MAX_FILES_PER_TECHNOLOGY = 2
