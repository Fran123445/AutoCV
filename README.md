# AutoCV

Tailor a résumé to a job posting from structured evidence instead of a wall of prose.

AutoCV extracts saved LinkedIn job postings and a candidate's own history into one normalized SQLite base, uses an LLM to tag both sides against shared taxonomies of technologies, concepts, roles, seniority and degrees, then writes and prints a résumé aimed at a specific posting. The résumé writer receives the posting's text alongside the candidate's structured work history, projects and skills, and selects relevant evidence for the document.

## How it works

Four pipelines feed one database and read back out of it. Each is an independent `extract → transform → load` script; the résumé pipeline is `write → render → pdf`.

```
                 seeds/ ──► db_creation.py ──► autocv.db (schema + taxonomies)
                                                   │
 LinkedIn HTML ──► jobs_etl.py ────────────────────┤   FactJob + requirements
 git repos ──────► projects_etl.py ────────────────┤   Project + evidence
 experience.toml ─► experience_etl.py ─────────────┤   FactExperience + Project
                                                   │
                                                   ▼
                              resume_etl.py (one candidate × one posting) ──► resume.pdf
```

| Pipeline | Source | Produces |
|----------|--------|----------|
| `jobs_etl.py` | Saved LinkedIn posting pages (`.html` / `.mhtml`) | `FactJob` rows with tagged technology / concept / degree requirements, role and seniority |
| `projects_etl.py` | A folder of git repos (at any depth) | `Project` rows with technology / concept evidence |
| `experience_etl.py` | One hand-written `experience.toml` | `FactExperience` and its `Project` rows |
| `resume_etl.py` | The loaded base, one `--user-id` × one `--job-id` | `resume.json` → `resume.html` → `resume.pdf` |

The LLM work lives in `llm/tasks/`, one package per identifier (technologies, concepts, roles, seniority, degrees) and per narrator. The heavier identifiers run a two-pass shape: a first extraction pass, a second review pass hunting for what the first missed, then a merge. Every model call is recorded to the run tables (`FactRun`, `FactJobRun`, `FactLLMCall`) with timings, token usage and a prompt hash, so a run is auditable after the fact.

## Setup

Requires Python 3.12+ and a running chat-completions endpoint. The default target is a local [llama-server](https://github.com/ggml-org/llama.cpp); any OpenAI-compatible `/v1/chat/completions` server works.

```bash
pip install -r requirements.txt
cp .env.example .env   # edit if your server is not at http://localhost:5001
```

The PDF stage needs [WeasyPrint](https://weasyprint.org/) and its Pango/Cairo system libraries. Only the `pdf` stage imports it, so the rest of the pipeline runs on a machine without it.

Every value in `.env` shows its default, so an empty file behaves the same as none. Key knobs:

- `AUTOCV_BASE_URL` — where the model lives (default `http://localhost:5001`)
- `AUTOCV_PROVIDER` — `llama-server` or `openrouter` (default `llama-server`)
- `AUTOCV_MODEL_NAME` / `AUTOCV_API_KEY` — default model and credentials; leave blank for a local unauthenticated server
- `AUTOCV_JOBS_MODEL_NAME`, `AUTOCV_EXPERIENCE_MODEL_NAME`, `AUTOCV_PROJECTS_MODEL_NAME`, `AUTOCV_RESUME_MODEL_NAME` — optional model overrides for an individual pipeline
- `AUTOCV_MAX_CONCURRENCY` — postings transformed at once; locally, match your llama-server `--parallel` slot count
- `AUTOCV_DATA_DIR` — base for the generated `data/` tree (all of it is derivable and gitignored)

## Usage

Create the database and load the taxonomies (idempotent — safe to re-run over a base that already holds data):

```bash
python db_creation.py
```

Load the candidate's own history. Fill in `templates/experience.toml` first (see `templates/experience.example.toml` for the level of detail that pays off), and point `AUTOCV_EXPERIENCE_PATH` at it or place it as `experience.toml` at the repo root:

```bash
python experience_etl.py
```

Ingest job postings — drop saved LinkedIn pages into `data/staging/`, then:

```bash
python jobs_etl.py
```

After a posting is extracted successfully, its source `.html` or `.mhtml` file
moves to `data/processed_jobs/`. Files that fail extraction remain in staging
for inspection or retry.

Ingest personal projects from a folder of repos:

```bash
python projects_etl.py --projects-dir /path/to/your/code
```

Generate a résumé for a candidate against a posting:

```bash
python resume_etl.py --user-id 1 --job-id 7
```

Each pipeline accepts a subset of stages as positional arguments — they always run in pipeline order regardless of how you list them:

```bash
python jobs_etl.py transform load     # skip re-extracting
python resume_etl.py render pdf --user-id 1 --job-id 7   # re-print without re-calling the model
```

The stage split follows the cost: only `transform` (jobs/projects) and `write` (résumé) call the model, so template, stylesheet or schema edits re-run the cheap stages without paying for the LLM a second time. Loads dedupe on a natural key (`linkedin_job_id`, repo path, `experience.toml` block id), so re-running over the same directory does not duplicate rows. Personal projects are updated in place on a repo-path match, including replacement of their technology and concept evidence.

## Data model

One star schema in `schema.sql`. Job requirements and candidate evidence share the same dimension tables (`DimTechnologies`, `DimConcepts`, `DimRole`, `DimSeniority`, `DimDegree`) for consistent tagging. Dependency bridges (`TechnologyDependency`, `ConceptDependency`, `TechnologyConcept`) store taxonomy relationships such as *react* implying *javascript* and *power bi* implying *business intelligence*. Résumé generation reads the posting's raw text and the candidate's stored evidence; it does not traverse those dependency bridges.

## Layout

```
config.py              Paths and shared filesystem configuration
db_creation.py         Schema + taxonomy seeding (idempotent)
schema.sql             The star schema
seeds/                 Canonical taxonomies (technologies, concepts, roles, ...)
*_etl.py               The four pipeline entry points
etl/                   Extract/transform/load stages per pipeline
llm/                   Settings, HTTP client, and the per-task model packages
resume_generator/      Résumé document model, HTML render, PDF print
templates/             experience.toml template + résumé HTML/CSS
run_log.py             Run-table telemetry wrappers
eval/                  Transform golden-file fixtures per pipeline
test/                  Extract/load tests
```

## Tests

```bash
pytest
```
