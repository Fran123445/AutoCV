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

CREATE TABLE IF NOT EXISTS ConceptDependency (
    child_id  INTEGER NOT NULL REFERENCES DimConcepts(id),  -- 'dashboarding'
    parent_id INTEGER NOT NULL REFERENCES DimConcepts(id),  -- implica 'business intelligence'
    PRIMARY KEY (child_id, parent_id)
);

-- El aviso pide el paraguas ('relational databases') y el candidato declara la
-- herramienta ('sql server'): sin este puente el match da 0 en algo que sabe.
-- Sólo implicaciones ciertas: 'power bi' implica business intelligence, no
-- implica machine learning porque alguien lo use para un modelo.
CREATE TABLE IF NOT EXISTS TechnologyConcept (
    technology_id INTEGER NOT NULL REFERENCES DimTechnologies(id),
    concept_id    INTEGER NOT NULL REFERENCES DimConcepts(id),
    PRIMARY KEY (technology_id, concept_id)
);

CREATE TABLE IF NOT EXISTS DimDegree (
    id     INTEGER PRIMARY KEY,
    name   TEXT NOT NULL UNIQUE,  -- canónico: 'computer science', 'information systems engineering', ...
    level  TEXT,                  -- 'high school' | 'bachelor' | 'master' | 'phd' | ...
    field  TEXT                   -- área amplia: 'cs', 'engineering', 'math'. Permite
                   -- matchear 'cualquier master en cs' sin depender del nombre exacto
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

-- Un aviso pide varias carreras como alternativas: 'Ingeniería en Sistemas,
-- Ciencias de la Computación o afín'. Todas cuentan como aceptables (OR), sin
-- must-have vs nice-to-have: no hay exp por carrera ni jerarquía entre ellas,
-- por eso este bridge no lleva las columnas required/min_exp/max_exp de los
-- otros dos. Sin filas = el aviso no pide ninguna carrera, común en dev.
CREATE TABLE IF NOT EXISTS JobDegrees (
    job_id    INTEGER NOT NULL REFERENCES FactJob(id),
    degree_id INTEGER NOT NULL REFERENCES DimDegree(id),
    PRIMARY KEY (job_id, degree_id)
);

-- Lado candidato (el usuario). Multiuser desde el arranque aunque hoy haya uno
-- solo: user_id atado a todo evita un refactor si mañana entran más candidatos.

-- Todo lo de acá abajo de birth_date es de render, no de match: ninguna query
-- de matching va a joinear por un teléfono. Vive igual en la base y no sólo en
-- experience.toml porque el generador de CV lee de la base, no del TOML.
CREATE TABLE IF NOT EXISTS FactUser (
    id         INTEGER PRIMARY KEY,
    full_name  TEXT,
    email      TEXT,
    phone      TEXT,
    location   TEXT,  -- ciudad y país como van en el CV, no dirección postal
    birth_date TEXT   -- ISO 8601
);

-- Links del CV: github, linkedin, portfolio, blog, etc.
CREATE TABLE IF NOT EXISTS UserLink (
    user_id    INTEGER NOT NULL REFERENCES FactUser(id),
    kind       TEXT NOT NULL,  -- 'github' | 'linkedin' | 'portfolio' | ...
                               -- abierto a propósito: no hay seed que valga la
                               -- pena mantener para cuatro valores
    url        TEXT NOT NULL,
    PRIMARY KEY (user_id, kind)
);

CREATE TABLE IF NOT EXISTS UserEducation (
    user_id     INTEGER NOT NULL REFERENCES FactUser(id),
    degree_id   INTEGER NOT NULL REFERENCES DimDegree(id),
    institution TEXT,
    gpa         TEXT,   -- como se imprime, con su escala: '8.48 / 10', '3.7/4.0'.
                -- TEXT y no REAL para mantener la escala
    start_date  TEXT,   -- ISO 8601
    end_date    TEXT,   -- null = en curso
    PRIMARY KEY (user_id, degree_id, institution)
);

-- Idiomas hablados. Sin dim y sin nivel canónico, como UserLink: no se matchea
-- contra nada (FactJob.language es el idioma del aviso, no un requisito), así
-- que name y level salen impresos tal cual se escribieron.
CREATE TABLE IF NOT EXISTS UserLanguage (
    user_id INTEGER NOT NULL REFERENCES FactUser(id),
    name    TEXT NOT NULL,  -- 'English', 'Spanish', ... como va en el CV
    level   TEXT,           -- como se imprime: 'Native', 'C1', 'B2 (Upper-intermediate)'
    PRIMARY KEY (user_id, name)
);

-- Bridges de skills. proficiency vive acá, no en los projects:
-- el project es evidencia de uso, el nivel es una afirmación del candidato.
CREATE TABLE IF NOT EXISTS UserTechnologies (
    user_id       INTEGER NOT NULL REFERENCES FactUser(id),
    technology_id INTEGER NOT NULL REFERENCES DimTechnologies(id),
    proficiency   INTEGER,   -- 1-5, misma escala en todo el lado usuario
    PRIMARY KEY (user_id, technology_id)
);

CREATE TABLE IF NOT EXISTS UserConcepts (
    user_id     INTEGER NOT NULL REFERENCES FactUser(id),
    concept_id  INTEGER NOT NULL REFERENCES DimConcepts(id),
    proficiency INTEGER,   -- 1-5
    PRIMARY KEY (user_id, concept_id)
);

-- Historia laboral. Simétrico con FactJob: mismas dims (company/role/seniority)
-- así el match candidato vs aviso compara peras con peras.
CREATE TABLE IF NOT EXISTS FactExperience (
    id           INTEGER PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES FactUser(id),
    source_id    TEXT,   -- id del bloque en experience.toml: la clave de dedupe
                 -- del ETL, como linkedin_job_id en FactJob. Un puesto no tiene
                 -- id natural, y company + role + fechas no alcanza: dos
                 -- pasajes por el mismo puesto son dos bloques distintos
    company_id   INTEGER REFERENCES DimCompany(id),   -- reusa DimCompany
    role_id      INTEGER REFERENCES DimRole(id), -- categoria dentro de la taxonomia cerrada
    job_title    TEXT,   -- el título real del puesto, como lo imprime el CV.
    seniority_id INTEGER REFERENCES DimSeniority(id),
    start_date   TEXT,   -- ISO 8601
    end_date     TEXT,   -- null = actual
    day_to_day   TEXT,   -- narrado, no crudo: el crudo vive en experience.toml.
                 -- Los tags que salen de esta prosa van a UserTechnologies y
                 -- UserConcepts, pero los tags alcanzan para matchear y no para
                 -- escribir. Sin la prosa, un match que no tiene un Project
                 -- atrás deja al generador de CV con una etiqueta y ninguna
                 -- histori.
    UNIQUE (user_id, source_id)   -- por usuario y no global: el id sale de un
           -- archivo que cada candidato escribe solo, y nada impide que dos
           -- elijan el mismo. Null en filas cargadas a mano, y los null son
           -- distintos entre sí en sqlite, así que no chocan
);

CREATE TABLE IF NOT EXISTS Project (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES FactUser(id),  -- denormalizado: los
                  -- projects personales (experience_id null) igual saben de quién son
    experience_id INTEGER REFERENCES FactExperience(id),     -- null = personal
    task_desc     TEXT NOT NULL,
    source_path   TEXT UNIQUE,  -- repo del que salió; null = cargado a mano
                  -- (varios null conviven). Clave de dedupe del ETL, igual que
                  -- linkedin_job_id en FactJob
    source_id     TEXT,         -- la otra clave de dedupe: id del bloque en
                  -- experience.toml, para los projects que nacen de un job.
                  -- Null en los personales, que no salen de ese archivo
    head_commit   TEXT,         -- hash del HEAD del repo (combinado si son varios). 
    UNIQUE (experience_id, source_id)   -- por experiencia y no global: los ids
           -- del archivo son únicos dentro de cada job, no entre jobs
);

-- Bridges de evidencia: qué tech/concepto tocó cada project. Sin proficiency;
-- eso vive en UserTechnologies/UserConcepts. Los techs de un project deberían
-- estar contenidos en los del usuario (rollup), no al revés.
CREATE TABLE IF NOT EXISTS ProjectTechnologies (
    project_id    INTEGER NOT NULL REFERENCES Project(id),
    technology_id INTEGER NOT NULL REFERENCES DimTechnologies(id),
    descr         TEXT,   -- rol de esta tech en el project: 'state del
                  -- dashboard', 'cola de jobs async'. Frase corta, no relato:
                  -- el relato vive en Project.task_desc. Null en deps triviales
                  -- (igual cuentan como tag para el match, sin narrativa)
    PRIMARY KEY (project_id, technology_id)
);

CREATE TABLE IF NOT EXISTS ProjectConcepts (
    project_id INTEGER NOT NULL REFERENCES Project(id),
    concept_id INTEGER NOT NULL REFERENCES DimConcepts(id),
    descr      TEXT,   -- como ProjectTechnologies.descr. Pesa más acá: un tag
               -- de concepto ('caching', 'machine learning') dice poco sin el
               -- contexto de cómo se aplicó en este project
    PRIMARY KEY (project_id, concept_id)
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

CREATE TABLE IF NOT EXISTS FactLLMCall (
    id                INTEGER PRIMARY KEY,
    job_run_id        INTEGER NOT NULL REFERENCES FactJobRun(id),
    task_name         TEXT NOT NULL,        -- 'jobs.tech_identifier.first_pass', ...
    attempt           INTEGER NOT NULL DEFAULT 1,  -- todavía no hay reintentos,
                      -- pero sin contador un reintento parece fila duplicada
    started_at        TEXT NOT NULL,
    ended_at          TEXT,
    latency_ms        INTEGER,
    model_name        TEXT,                 -- el que devolvió el server, no el
                      -- que pediste: MODEL_NAME está vacío y elige el server
    temperature       REAL,
    think             INTEGER,              -- 0/1, lo único que varía por tarea
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,              -- incluye los de razonamiento:
                      -- llama-server no los separa en usage
    prompt_sha1       TEXT,                 -- hash del prompt renderizado; sin
                      -- esto una corrida vieja y una nueva sólo "dan distinto"
    http_status       INTEGER,
    status            TEXT NOT NULL DEFAULT 'running',
    error             TEXT
);

CREATE INDEX IF NOT EXISTS idx_experience_user ON FactExperience(user_id);
CREATE INDEX IF NOT EXISTS idx_project_user     ON Project(user_id);
CREATE INDEX IF NOT EXISTS idx_project_exp      ON Project(experience_id);
CREATE INDEX IF NOT EXISTS idx_jobrun_run     ON FactJobRun(run_id);
CREATE INDEX IF NOT EXISTS idx_llmcall_jr     ON FactLLMCall(job_run_id);
CREATE INDEX IF NOT EXISTS idx_llmcall_task   ON FactLLMCall(task_name);