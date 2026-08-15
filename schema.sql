-- Dimensiones
--
-- Todo va con IF NOT EXISTS: db_creation.py corre este archivo entero en cada
-- arranque, así una tabla nueva aparece sin tener que borrar la base.

CREATE TABLE IF NOT EXISTS DimCompany (
    id           INTEGER PRIMARY KEY,
    company_name TEXT NOT NULL UNIQUE,
    location     TEXT,
    size         TEXT
);

CREATE TABLE IF NOT EXISTS DimRole (
    id        INTEGER PRIMARY KEY,
    role_name TEXT NOT NULL UNIQUE   -- estandarizado: 'backend dev', 'bi dev', 'full stack dev', ...
);

CREATE TABLE IF NOT EXISTS DimSeniority (
    id              INTEGER PRIMARY KEY,
    label           TEXT NOT NULL UNIQUE,  -- 'junior', 'ssr', 'senior', 'lead'
    typical_min_exp INTEGER,               -- años típicos del label, ambos
    typical_max_exp INTEGER                -- nullable: muchas JDs dicen
                    -- 'Senior' sin años. 'typical' porque describen la palabra,
                    -- no ningún aviso: los años que pide un aviso concreto son
                    -- otra cosa y no viven acá
);

CREATE TABLE IF NOT EXISTS DimTechnologies (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE        -- nombre canónico: 'javascript', 'postgresql', ...
);

CREATE TABLE IF NOT EXISTS TechnologyDependency (
    child_id  INTEGER NOT NULL REFERENCES DimTechnologies(id),  -- 'react'
    parent_id INTEGER NOT NULL REFERENCES DimTechnologies(id),  -- implica 'javascript'
    PRIMARY KEY (child_id, parent_id)
);

CREATE TABLE IF NOT EXISTS DimConcepts (
    id           INTEGER PRIMARY KEY,
    concept_name TEXT NOT NULL UNIQUE  -- 'agile', 'machine learning', 'data structures', ...
);

-- Fact

CREATE TABLE IF NOT EXISTS FactJob (
    id                 INTEGER PRIMARY KEY,
    linkedin_job_id    INTEGER NOT NULL UNIQUE,  -- clave de dedupe; sale de la
                       -- URL guardada, no del cuerpo del HTML: ahí aparecen los
                       -- ids de los avisos recomendados
    position_name      TEXT NOT NULL,        -- título tal cual aparece en la JD
    company_id         INTEGER REFERENCES DimCompany(id),
    role_id            INTEGER REFERENCES DimRole(id),
    seniority_id       INTEGER REFERENCES DimSeniority(id),
    post_date          TEXT,                 -- ISO 8601, derivado de scrape_date
                       -- menos el tiempo transcurrido; precisión gruesa
    post_date_raw      TEXT,                 -- 'hace 3 meses' tal cual
    scrape_date        TEXT NOT NULL,
    source_url         TEXT,
    location           TEXT,                 -- ubicación del puesto, no de la empresa
    days_at_the_office INTEGER,              -- null = no especificado, 0 = full remote
    language           TEXT,                 -- 'en', 'es', ...
    salary_min         INTEGER,
    salary_max         INTEGER,
    salary_currency    TEXT,
    status             TEXT NOT NULL DEFAULT 'scraped',
                       -- 'scraped' | 'applied' | 'rejected' | 'interview' | 'discarded'
    raw_text           TEXT NOT NULL         -- siempre: permite re-extraer si mejorás el schema
);

-- Bridges (N:M job ↔ tech/concept)

CREATE TABLE IF NOT EXISTS JobTechnologies (
    job_id        INTEGER NOT NULL REFERENCES FactJob(id),
    technology_id INTEGER NOT NULL REFERENCES DimTechnologies(id),
    required      INTEGER NOT NULL DEFAULT 1,  -- 1 = must-have, 0 = nice-to-have
    min_exp       INTEGER,                     -- años por tecnología; casi siempre null
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

-- Observabilidad de corridas

CREATE TABLE IF NOT EXISTS FactRun (
    id              INTEGER PRIMARY KEY,
    stage           TEXT NOT NULL,          -- 'extract' | 'transform' | 'load'
    started_at      TEXT NOT NULL,          -- ISO 8601, como el resto
    ended_at        TEXT,                   -- null = corriendo, o muerta
    status          TEXT NOT NULL DEFAULT 'running',
                    -- 'running' | 'completed' | 'failed'
    postings_total  INTEGER,
    postings_ok     INTEGER,
    postings_failed INTEGER,
    max_concurrency INTEGER,
    config_json     TEXT,                   -- snapshot de llm/config.py: model,
                    -- temperature, timeout, base_url. Un JSON y no columnas
                    -- sueltas: la config cambia más seguido que el schema
    git_commit      TEXT,                   -- qué código produjo estos datos
    error           TEXT
);

CREATE TABLE IF NOT EXISTS FactJobRun (
    id          INTEGER PRIMARY KEY,
    run_id      INTEGER NOT NULL REFERENCES FactRun(id),
    source_file TEXT NOT NULL,              -- stem del json; en transform
                -- todavía no existe el FactJob al que apuntar
    job_id      INTEGER REFERENCES FactJob(id),  -- se completa en load
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    status      TEXT NOT NULL DEFAULT 'running',
    error       TEXT                        -- repr de la excepción
);

CREATE TABLE IF NOT EXISTS FactAgentCall (
    id                INTEGER PRIMARY KEY,
    job_run_id        INTEGER NOT NULL REFERENCES FactJobRun(id),
    agent_name        TEXT NOT NULL,        -- 'tech_identifier.first_pass', ...
    attempt           INTEGER NOT NULL DEFAULT 1,  -- todavía no hay reintentos,
                      -- pero sin contador un reintento parece fila duplicada
    started_at        TEXT NOT NULL,
    ended_at          TEXT,
    latency_ms        INTEGER,
    model_name        TEXT,                 -- el que devolvió el server, no el
                      -- que pediste: MODEL_NAME está vacío y elige el server
    temperature       REAL,
    think             INTEGER,              -- 0/1, lo único que varía por agente
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,              -- incluye los de razonamiento:
                      -- llama-server no los separa en usage
    prompt_sha1       TEXT,                 -- hash del prompt renderizado; sin
                      -- esto una corrida vieja y una nueva sólo "dan distinto"
    http_status       INTEGER,
    status            TEXT NOT NULL DEFAULT 'running',
    error             TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobrun_run   ON FactJobRun(run_id);
CREATE INDEX IF NOT EXISTS idx_agentcall_jr ON FactAgentCall(job_run_id);
CREATE INDEX IF NOT EXISTS idx_agentcall_ag ON FactAgentCall(agent_name);