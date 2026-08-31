"""
Everything every pipeline agrees on: the paths, anchored to this file rather
than to the working directory so a stage run from anywhere finds the same base
and staging folders, and the endpoint the model is reached through.
"""

from pathlib import Path

import os

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).parent

# Explicit path, not the walk-up default: a stage run from another directory
# would otherwise pick up whatever .env sits above it, or none at all. Real
# environment variables always win over the file.
load_dotenv(ROOT_DIR / ".env")
SCHEMA_PATH = ROOT_DIR / "schema.sql"
SEEDS_DIR = ROOT_DIR / "seeds"

# Overridable so a run can be pointed at a scratch copy without touching a
# tracked file. Gitignored: everything under it is derivable from seeds/ plus
# the scraped HTML.
DATA_DIR = Path(os.getenv("AUTOCV_DATA_DIR") or ROOT_DIR / "data")

DB_PATH = DATA_DIR / "autocv.db"

STAGING_DIR = DATA_DIR / "staging"
# Source pages that completed job extraction. Keeping these out of staging
# makes the staging folder represent only work that still needs processing.
JOBS_PROCESSED_DIR = DATA_DIR / "processed_jobs"
JOBS_EXTRACT_DIR = DATA_DIR / "extracted_descs"
JOBS_TRANSFORM_DIR = DATA_DIR / "transformed_descs"
PROJECTS_EXTRACT_DIR = DATA_DIR / "extracted_projects"
PROJECTS_TRANSFORM_DIR = DATA_DIR / "transformed_projects"
# No extract counterpart: the experience file is already the structured artifact.
EXPERIENCE_TRANSFORM_DIR = DATA_DIR / "transformed_experience"

RESUMES_DIR = DATA_DIR / "resume"

# La plantilla llena, escrita a mano. Deliberadamente fuera de DATA_DIR: todo lo
# que cuelga de ahí es derivable y descartable, y esto es lo contrario — es
# fuente, y la única del pipeline que ninguna corrida puede regenerar.
# templates/experience.toml es la copia en blanco, y esa sí está trackeada.
EXPERIENCE_PATH = Path(os.getenv("AUTOCV_EXPERIENCE_PATH") or ROOT_DIR / "experience.toml")
TEMPLATES_DIR = ROOT_DIR / "templates"


# ============================================================================
# Model endpoint
# ============================================================================

# Where the chat completions endpoint lives. The local default is llama-server.
BASE_URL = os.getenv("AUTOCV_BASE_URL", "http://localhost:5001")
CHAT_COMPLETIONS_PATH = "/v1/chat/completions"

API_KEY = os.getenv("AUTOCV_API_KEY", "")
MODEL_NAME = os.getenv("AUTOCV_MODEL_NAME", "")

# `or` rather than a getenv default: a variable left blank in .env arrives as an
# empty string, which is a default the caller meant, not a number.
TIMEOUT = float(os.getenv("AUTOCV_TIMEOUT") or 300)
TEMPERATURE = float(os.getenv("AUTOCV_TEMPERATURE") or 1)

# Postings transformed at once. Locally this should match llama-server's
# --parallel slot count: past that the extra requests only queue, and the
# server splits its KV cache across the slots, so each one holds less context.
# Raise it once BASE_URL points somewhere hosted.
MAX_CONCURRENCY = int(os.getenv("AUTOCV_MAX_CONCURRENCY") or 4)

# Reasoning effort per task, keyed by the task_name post_chat is called with.
# "low", "medium" or "high", or "none" to turn reasoning off. Every task that
# calls the model is listed: post_chat refuses a task it has no entry for rather
# than guess a default, so adding a pass means deciding here how hard it thinks.
# Code and not env, like the pipeline's other tuning tables: the right effort
# for a pass is a property of the pass, not the deploy.
REASONING_EFFORT_BY_TASK = {
    "resume.write": "low",
    "experience.tech_identifier.day_to_day": "low",
    "experience.tech_identifier.project": "low",
    "experience.project_describer.describe": "low",
    "experience.project_narrator.narrate": "low",
    "experience.day_to_day_narrator.narrate": "low",
    "jobs.tech_identifier.first_pass": "low",
    "jobs.tech_identifier.second_pass": "low",
    "jobs.concept_identifier.first_pass": "low",
    "jobs.concept_identifier.second_pass": "low",
    "projects.analyzer.analyze": "low",
    "jobs.role_identifier.classify": "none",
    "jobs.seniority_identifier.classify": "none",
    "jobs.degree_identifier.classify": "none",
}
