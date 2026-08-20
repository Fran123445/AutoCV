"""
Paths every pipeline agrees on. Anchored to this file rather than to the working
directory, so a stage run from anywhere still finds the same base and the same
staging folders.
"""

from pathlib import Path

import os

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).parent

# Explicit path, not the walk-up default: a stage run from another directory
# would otherwise pick up whatever .env sits above it, or none at all. Called
# again in llm/config.py, which reads its own variables and does not import this
# module. Real environment variables always win over the file.
load_dotenv(ROOT_DIR / ".env")
SCHEMA_PATH = ROOT_DIR / "schema.sql"
SEEDS_DIR = ROOT_DIR / "seeds"

# Overridable so a run can be pointed at a scratch copy without touching a
# tracked file. Gitignored: everything under it is derivable from seeds/ plus
# the scraped HTML.
DATA_DIR = Path(os.getenv("AUTOCV_DATA_DIR") or ROOT_DIR / "data")

DB_PATH = DATA_DIR / "autocv.db"

STAGING_DIR = DATA_DIR / "staging"
JOBS_EXTRACT_DIR = DATA_DIR / "extracted_descs"
JOBS_TRANSFORM_DIR = DATA_DIR / "transformed_descs"
PROJECTS_EXTRACT_DIR = DATA_DIR / "extracted_projects"
PROJECTS_TRANSFORM_DIR = DATA_DIR / "transformed_projects"
# No extract counterpart: the experience file is already the structured artifact.
EXPERIENCE_TRANSFORM_DIR = DATA_DIR / "transformed_experience"

RESUMES_WRITE_DIR = DATA_DIR / "written_resumes"
RESUMES_RENDER_DIR = DATA_DIR / "rendered_resumes"

# La plantilla llena, escrita a mano. Deliberadamente fuera de DATA_DIR: todo lo
# que cuelga de ahí es derivable y descartable, y esto es lo contrario — es
# fuente, y la única del pipeline que ninguna corrida puede regenerar.
# templates/experience.toml es la copia en blanco, y esa sí está trackeada.
EXPERIENCE_PATH = Path(os.getenv("AUTOCV_EXPERIENCE_PATH") or ROOT_DIR / "experience.toml")
TEMPLATES_DIR = ROOT_DIR / "templates"
