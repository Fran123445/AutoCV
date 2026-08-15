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
# without a Cargo.toml still means Rust). Kept wide on purpose: a repo the agent
# should judge is better admitted than dropped over a missing extension.
SOURCE_EXTENSIONS = frozenset(
    {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".rb",
        ".php", ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".kt", ".scala",
        ".swift", ".m", ".sql", ".sh", ".r", ".ipynb", ".vue", ".svelte",
    }
)

# A repo under this many source files and with no manifest is treated as junk
# (scratch, config-only, empty scaffold) and never reaches the agent.
MIN_SOURCE_FILES = 3

# README is narrative fuel for the task_desc pass, not a parse target; cap it so
# a monster readme cannot blow up the dict handed downstream.
README_MAX_CHARS = 20_000
