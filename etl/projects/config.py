# Tunables for the projects extract stage: which files count as source, and
# where the junk floor sits. Kept out of extract.py so the knobs move without
# touching the walk logic.

# Counted only for the cull floor (many .rs without a Cargo.toml still means
# Rust). Kept wide on purpose: a repo the model should judge is better admitted
# than dropped over a missing extension.
SOURCE_EXTENSIONS = frozenset(
    {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".rb",
        ".php", ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".kt", ".scala",
        ".swift", ".m", ".sql", ".sh", ".r", ".ipynb", ".vue", ".svelte",
    }
)

# A repo under this many source files is treated as junk (scratch, config-only,
# empty scaffold) and never reaches the model.
MIN_SOURCE_FILES = 3

# Directory names the repo walk never descends into while hunting for a .git.
# A repo sits at the top of its own tree, so these only ever hide a dependency
# checkout or build junk, and crawling a node_modules tree for a .git that is
# not there is the one way this walk could turn slow.
WALK_PRUNE_DIRS = frozenset({".git", "node_modules", "venv", ".venv", "__pycache__"})

