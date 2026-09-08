-- Dimensions
--
-- Everything uses IF NOT EXISTS: db_creation.py runs this whole file on every
-- startup, so a new table shows up without dropping the database.

CREATE TABLE IF NOT EXISTS DimCompany (
    id           INTEGER PRIMARY KEY,
    company_name TEXT NOT NULL UNIQUE,
    location     TEXT,
    size         TEXT
);

CREATE TABLE IF NOT EXISTS DimRole (
    id        INTEGER PRIMARY KEY,
    role_name TEXT NOT NULL UNIQUE   -- standardized: 'backend dev', 'bi dev', 'full stack dev', ...
);

CREATE TABLE IF NOT EXISTS DimSeniority (
    id              INTEGER PRIMARY KEY,
    label           TEXT NOT NULL UNIQUE,  -- 'junior', 'ssr', 'senior', 'lead'
    typical_min_exp INTEGER,               -- typical years for the label, both
    typical_max_exp INTEGER                -- nullable: many JDs say 'Senior'
                    -- with no years. 'typical' because they describe the word,
                    -- not any posting: the years a concrete posting asks for
                    -- are a different thing and don't live here
);

CREATE TABLE IF NOT EXISTS DimTechnologies (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE        -- canonical name: 'javascript', 'postgresql', ...
);

CREATE TABLE IF NOT EXISTS TechnologyDependency (
    child_id  INTEGER NOT NULL REFERENCES DimTechnologies(id),  -- 'react'
    parent_id INTEGER NOT NULL REFERENCES DimTechnologies(id),  -- implies 'javascript'
    PRIMARY KEY (child_id, parent_id)
);

CREATE TABLE IF NOT EXISTS DimConcepts (
    id           INTEGER PRIMARY KEY,
    concept_name TEXT NOT NULL UNIQUE  -- 'agile', 'machine learning', 'data structures', ...
);

CREATE TABLE IF NOT EXISTS ConceptDependency (
    child_id  INTEGER NOT NULL REFERENCES DimConcepts(id),  -- 'dashboarding'
    parent_id INTEGER NOT NULL REFERENCES DimConcepts(id),  -- implies 'business intelligence'
    PRIMARY KEY (child_id, parent_id)
);

-- The posting asks for the umbrella ('relational databases') and the candidate
-- declares the tool ('sql server'): without this bridge the match scores 0 on
-- something they know. Only certain implications: 'power bi' implies business
-- intelligence, it doesn't imply machine learning because someone used it for
-- a model.
CREATE TABLE IF NOT EXISTS TechnologyConcept (
    technology_id INTEGER NOT NULL REFERENCES DimTechnologies(id),
    concept_id    INTEGER NOT NULL REFERENCES DimConcepts(id),
    PRIMARY KEY (technology_id, concept_id)
);

CREATE TABLE IF NOT EXISTS DimDegree (
    id     INTEGER PRIMARY KEY,
    name   TEXT NOT NULL UNIQUE,  -- canonical: 'computer science', 'information systems engineering', ...
    level  TEXT,                  -- 'high school' | 'bachelor' | 'master' | 'phd' | ...
    field  TEXT                   -- broad area: 'cs', 'engineering', 'math'. Allows
                   -- matching 'any master in cs' without relying on the exact name
);

-- Human-facing degree names. DimDegree.name stays canonical and language
-- neutral for matching; this table carries the display spelling per locale.
CREATE TABLE IF NOT EXISTS DimDegreeTranslation (
    id        INTEGER PRIMARY KEY,
    degree_id INTEGER NOT NULL REFERENCES DimDegree(id),
    locale    TEXT NOT NULL CHECK (length(trim(locale)) > 0),
    name      TEXT NOT NULL CHECK (length(trim(name)) > 0),
    UNIQUE (degree_id, locale)
);

-- Fact

CREATE TABLE IF NOT EXISTS FactJob (
    id                 INTEGER PRIMARY KEY,
    source             TEXT NOT NULL,            -- linkedin, indeed, ...
    source_job_id      TEXT NOT NULL,            -- source-local id from the URL
    position_name      TEXT NOT NULL,        -- title as it appears in the JD
    company_id         INTEGER REFERENCES DimCompany(id),
    role_id            INTEGER REFERENCES DimRole(id),
    seniority_id       INTEGER REFERENCES DimSeniority(id),
    post_date          TEXT,                 -- ISO 8601, derived from scrape_date
                       -- minus the elapsed time; coarse precision
    post_date_raw      TEXT,                 -- '3 months ago' verbatim
    scrape_date        TEXT NOT NULL,
    source_url         TEXT,
    location           TEXT,                 -- location of the position, not the company
    days_at_the_office INTEGER,              -- null = unspecified, 0 = full remote
    language           TEXT,                 -- 'en', 'es', ...
    salary_min         INTEGER,
    salary_max         INTEGER,
    salary_currency    TEXT,
    status             TEXT NOT NULL DEFAULT 'scraped',
                       -- 'scraped' | 'applied' | 'rejected' | 'interview' | 'discarded'
    raw_text           TEXT NOT NULL,        -- always: allows re-extracting if you improve the schema
    UNIQUE (source, source_job_id)           -- dedupe within each source
);

-- Bridges (N:M job <-> tech/concept)

CREATE TABLE IF NOT EXISTS JobTechnologies (
    job_id        INTEGER NOT NULL REFERENCES FactJob(id),
    technology_id INTEGER NOT NULL REFERENCES DimTechnologies(id),
    required      INTEGER NOT NULL DEFAULT 1,  -- 1 = must-have, 0 = nice-to-have
    min_exp       INTEGER,                     -- years per technology; almost always null
    max_exp       INTEGER,
    PRIMARY KEY (job_id, technology_id)
);

CREATE TABLE IF NOT EXISTS JobConcepts (
    job_id     INTEGER NOT NULL REFERENCES FactJob(id),
    concept_id INTEGER NOT NULL REFERENCES DimConcepts(id),
    required   INTEGER NOT NULL DEFAULT 1,
    min_exp    INTEGER,
    max_exp    INTEGER,
    PRIMARY KEY (job_id, concept_id)
);

-- A posting asks for several degrees as alternatives: 'Systems Engineering,
-- Computer Science or related'. All count as acceptable (OR), with no
-- must-have vs nice-to-have: there's no exp per degree and no hierarchy among
-- them, so this bridge doesn't carry the required/min_exp/max_exp columns the
-- other two have. No rows = the posting asks for no degree, common in dev.
CREATE TABLE IF NOT EXISTS JobDegrees (
    job_id    INTEGER NOT NULL REFERENCES FactJob(id),
    degree_id INTEGER NOT NULL REFERENCES DimDegree(id),
    PRIMARY KEY (job_id, degree_id)
);

-- Candidate side (the user). Multiuser from the start even though today
-- there's only one: user_id tied to everything avoids a refactor if more
-- candidates show up tomorrow.

-- Everything below birth_date is for rendering, not matching: no matching
-- query will join on a phone number. It lives in the database anyway and not
-- only in experience.toml because the CV generator reads from the database,
-- not the TOML.
CREATE TABLE IF NOT EXISTS FactUser (
    id         INTEGER PRIMARY KEY,
    full_name  TEXT,
    email      TEXT,
    phone      TEXT,
    location   TEXT,  -- city and country as they go in the CV, not postal address
    birth_date TEXT   -- ISO 8601
);

-- CV links: github, linkedin, portfolio, blog, etc.
CREATE TABLE IF NOT EXISTS UserLink (
    user_id    INTEGER NOT NULL REFERENCES FactUser(id),
    kind       TEXT NOT NULL,  -- 'github' | 'linkedin' | 'portfolio' | ...
                               -- open on purpose: no seed worth maintaining for
                               -- four values
    url        TEXT NOT NULL,
    PRIMARY KEY (user_id, kind)
);

CREATE TABLE IF NOT EXISTS UserEducation (
    user_id     INTEGER NOT NULL REFERENCES FactUser(id),
    degree_id   INTEGER NOT NULL REFERENCES DimDegree(id),
    institution TEXT,
    gpa         TEXT,   -- as printed, with its scale: '8.48 / 10', '3.7/4.0'.
                -- TEXT and not REAL to keep the scale
    start_date  TEXT,   -- ISO 8601
    end_date    TEXT,   -- null = ongoing
    PRIMARY KEY (user_id, degree_id, institution)
);

-- Spoken languages. No dim and no canonical level, like UserLink: it isn't
-- matched against anything (FactJob.language is the posting's language, not a
-- requirement), so name and level print exactly as written.
CREATE TABLE IF NOT EXISTS UserLanguage (
    user_id INTEGER NOT NULL REFERENCES FactUser(id),
    name    TEXT NOT NULL,  -- 'English', 'Spanish', ... as it goes in the CV
    level   TEXT,           -- as printed: 'Native', 'C1', 'B2 (Upper-intermediate)'
    PRIMARY KEY (user_id, name)
);

-- Skill bridges. proficiency lives here, not in the projects: the project is
-- evidence of use, the level is a claim by the candidate.
CREATE TABLE IF NOT EXISTS UserTechnologies (
    user_id       INTEGER NOT NULL REFERENCES FactUser(id),
    technology_id INTEGER NOT NULL REFERENCES DimTechnologies(id),
    proficiency   INTEGER,   -- 1-5, same scale across the whole user side
    PRIMARY KEY (user_id, technology_id)
);

CREATE TABLE IF NOT EXISTS UserConcepts (
    user_id     INTEGER NOT NULL REFERENCES FactUser(id),
    concept_id  INTEGER NOT NULL REFERENCES DimConcepts(id),
    proficiency INTEGER,   -- 1-5
    PRIMARY KEY (user_id, concept_id)
);

-- Work history. Symmetric with FactJob: same dims (company/role/seniority) so
-- the candidate vs posting match compares apples to apples.
CREATE TABLE IF NOT EXISTS FactExperience (
    id           INTEGER PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES FactUser(id),
    source_id    TEXT,   -- id of the block in experience.toml: the ETL's dedupe
                 -- key, like source_job_id in FactJob. A position has no
                 -- natural id, and company + role + dates isn't enough: two
                 -- stints in the same position are two distinct blocks
    company_id   INTEGER REFERENCES DimCompany(id),   -- reuses DimCompany
    role_id      INTEGER REFERENCES DimRole(id), -- category within the closed taxonomy
    job_title    TEXT,   -- the real position title, as the CV prints it.
    seniority_id INTEGER REFERENCES DimSeniority(id),
    start_date   TEXT,   -- ISO 8601
    end_date     TEXT,   -- null = current
    day_to_day   TEXT,   -- narrated, not raw: the raw lives in experience.toml.
                 -- The tags derived from this prose go to UserTechnologies and
                 -- UserConcepts, but tags are enough to match and not to write.
                 -- Without the prose, a match with no Project behind it leaves
                 -- the CV generator with a label and no story.
    UNIQUE (user_id, source_id)   -- per user and not global: the id comes from
           -- a file each candidate writes alone, and nothing stops two of them
           -- from picking the same one. Null in hand-loaded rows, and nulls
           -- differ from each other in sqlite, so they don't collide
);

CREATE TABLE IF NOT EXISTS Project (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES FactUser(id),  -- denormalized: personal
                  -- projects (experience_id null) still know whose they are
    experience_id INTEGER REFERENCES FactExperience(id),     -- null = personal
    task_desc     TEXT NOT NULL,
    source_path   TEXT UNIQUE,  -- repo it came from; null = hand-loaded (several
                  -- nulls coexist). The ETL's dedupe key, same as
                  -- source_job_id in FactJob
    source_id     TEXT,         -- the other dedupe key: id of the block in
                  -- experience.toml, for projects born from a job. Null in
                  -- personal ones, which don't come from that file
    head_commit   TEXT,         -- hash of the repo's HEAD (combined if several).
    first_commit_at TEXT,       -- ISO 8601 date of the first commit
    last_commit_at  TEXT,       -- ISO 8601 date of the last commit
    UNIQUE (experience_id, source_id)   -- per experience and not global: the
           -- file's ids are unique within each job, not across jobs
);

-- Evidence bridges: which tech/concept each project touched. No proficiency;
-- that lives in UserTechnologies/UserConcepts. A project's techs should be
-- contained in the user's (rollup), not the other way around.
CREATE TABLE IF NOT EXISTS ProjectTechnologies (
    project_id    INTEGER NOT NULL REFERENCES Project(id),
    technology_id INTEGER NOT NULL REFERENCES DimTechnologies(id),
    descr         TEXT,   -- this tech's role in the project
    PRIMARY KEY (project_id, technology_id)
);

CREATE TABLE IF NOT EXISTS ProjectConcepts (
    project_id INTEGER NOT NULL REFERENCES Project(id),
    concept_id INTEGER NOT NULL REFERENCES DimConcepts(id),
    descr      TEXT,   -- like ProjectTechnologies.descr.
    PRIMARY KEY (project_id, concept_id)
);

-- Run observability
--
-- Three grains, parent to child: a run is one stage of one pipeline, an item is
-- one unit of work inside that stage, a call is one request to the model. 

CREATE TABLE IF NOT EXISTS FactRun (
    id              INTEGER PRIMARY KEY,
    pipeline        TEXT NOT NULL,          -- 'jobs' | 'projects' | 'experience' | 'resume'
    stage           TEXT NOT NULL,          -- 'extract' | 'transform' | 'load',
                    -- and 'write' | 'render' | 'pdf' on the resume side.
    started_at      TEXT NOT NULL,          -- ISO 8601, like the rest
    ended_at        TEXT,                   -- null = running, or dead
    status          TEXT NOT NULL DEFAULT 'running',
                    -- 'running' | 'completed' | 'failed'
    items_total     INTEGER,                -- units of work, whatever the unit
    items_ok        INTEGER,                -- is for the pipeline: a posting, a
    items_failed    INTEGER,                -- repo, a file, one resume
    max_concurrency INTEGER,
    config_json     TEXT,                   -- snapshot of config.py: model,
                    -- temperature, timeout, base_url. One JSON and not loose
                    -- columns: the config changes more often than the schema
    git_commit      TEXT,                   -- which code produced this data
    error           TEXT
);

CREATE TABLE IF NOT EXISTS FactRunItem (
    id           INTEGER PRIMARY KEY,
    run_id       INTEGER NOT NULL REFERENCES FactRun(id),
    item_key     TEXT NOT NULL,             -- names the unit, and its not always
                 -- a file: a json stem on the pipelines that glob a folder, a
                 -- repo name on projects, a resume folder on the resume side
    entity_table TEXT,                      -- which row this item is about, as
    entity_id    INTEGER,                   -- 'FactJob' | 'Project' | ...
                 -- Both null on a stage that produces no single row. Named
                 -- rather than a real foreign key because the parent differs
                 -- per pipeline: one column each would grow with every new
                 -- pipeline and leave all but one null on every row. The cost
                 -- is that sqlite does not check it
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    status       TEXT NOT NULL DEFAULT 'running',
    error        TEXT                       -- repr of the exception
);

CREATE TABLE IF NOT EXISTS FactLLMCall (
    id                INTEGER PRIMARY KEY,
    run_item_id       INTEGER NOT NULL REFERENCES FactRunItem(id),
    task_name         TEXT NOT NULL,        -- 'jobs.tech_identifier.first_pass', ...
    attempt           INTEGER NOT NULL DEFAULT 1,  -- no retries yet, but without
                      -- a counter a retry looks like a duplicate row
    started_at        TEXT NOT NULL,
    ended_at          TEXT,
    latency_ms        INTEGER,
    model_name        TEXT,                 -- the one the server returned, not
                      -- the one you asked for: MODEL_NAME is empty and the
                      -- server picks
    temperature       REAL,
    reasoning_effort  TEXT,                 -- 'low' | 'medium' | 'high' |
                      -- 'none'. The one payload field that varies per task.
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,              -- includes reasoning ones:
                      -- llama-server does not split them out in usage
    prompt_sha1       TEXT,                 -- hash of the rendered prompt;
                      -- without it an old run and a new one just "differ"
    http_status       INTEGER,
    status            TEXT NOT NULL DEFAULT 'running',
    error             TEXT
);

CREATE INDEX IF NOT EXISTS idx_experience_user ON FactExperience(user_id);
CREATE INDEX IF NOT EXISTS idx_project_user     ON Project(user_id);
CREATE INDEX IF NOT EXISTS idx_project_exp      ON Project(experience_id);
CREATE INDEX IF NOT EXISTS idx_runitem_run    ON FactRunItem(run_id);
CREATE INDEX IF NOT EXISTS idx_runitem_entity ON FactRunItem(entity_table, entity_id);
CREATE INDEX IF NOT EXISTS idx_llmcall_item   ON FactLLMCall(run_item_id);
CREATE INDEX IF NOT EXISTS idx_llmcall_task   ON FactLLMCall(task_name);
