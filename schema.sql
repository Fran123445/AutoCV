-- Dimensiones

CREATE TABLE DimCompany (
    id           INTEGER PRIMARY KEY,
    company_name TEXT NOT NULL UNIQUE,
    location     TEXT,
    size         TEXT
);

CREATE TABLE DimRole (
    id        INTEGER PRIMARY KEY,
    role_name TEXT NOT NULL UNIQUE   -- estandarizado: 'backend dev', 'bi dev', 'full stack dev', ...
);

CREATE TABLE DimSeniority (
    id      INTEGER PRIMARY KEY,
    label   TEXT NOT NULL UNIQUE,    -- 'junior', 'ssr', 'senior', 'lead'
    min_exp INTEGER,                 -- años típicos del label, ambos nullable:
    max_exp INTEGER                  -- muchas JDs dicen 'Senior' sin años
);

CREATE TABLE DimTechnologies (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE        -- nombre canónico: 'javascript', 'postgresql', ...
);

CREATE TABLE TechnologyAlias (
    alias         TEXT PRIMARY KEY,  -- 'js', 'ecmascript', 'postgres', ...
    technology_id INTEGER NOT NULL REFERENCES DimTechnologies(id)
);

CREATE TABLE TechnologyDependency (
    child_id  INTEGER NOT NULL REFERENCES DimTechnologies(id),  -- 'react'
    parent_id INTEGER NOT NULL REFERENCES DimTechnologies(id),  -- implica 'javascript'
    PRIMARY KEY (child_id, parent_id)
);

CREATE TABLE DimConcepts (
    id           INTEGER PRIMARY KEY,
    concept_name TEXT NOT NULL UNIQUE  -- 'agile', 'machine learning', 'data structures', ...
);

-- Fact

CREATE TABLE FactJob (
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

CREATE TABLE JobTechnologies (
    job_id        INTEGER NOT NULL REFERENCES FactJob(id),
    technology_id INTEGER NOT NULL REFERENCES DimTechnologies(id),
    required      INTEGER NOT NULL DEFAULT 1,  -- 1 = must-have, 0 = nice-to-have
    min_exp       INTEGER,                     -- años por tecnología; casi siempre null
    max_exp       INTEGER,
    PRIMARY KEY (job_id, technology_id)
);

CREATE TABLE JobConcepts (
    job_id     INTEGER NOT NULL REFERENCES FactJob(id),
    concept_id INTEGER NOT NULL REFERENCES DimConcepts(id),
    required   INTEGER NOT NULL DEFAULT 1,
    min_exp    INTEGER,
    max_exp    INTEGER,
    PRIMARY KEY (job_id, concept_id)
);