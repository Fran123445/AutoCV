import sqlite3

from config import DB_PATH, SCHEMA_PATH
from llm.seeds import load_seed


def _create_schema(connection: sqlite3.Connection):
    """
    Create the database schema by executing the SQL statements in the schema.sql file.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
    """
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def _load_seniority_data(connection: sqlite3.Connection) -> int:
    """
    Load the seniority data into the DimSeniority table.

    The only registry whose rows carry more than a name, so it is also the only
    one that updates on conflict: retuning a label's year range in the seed
    should reach a base that already has the label.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
    """
    seniorities = load_seed("seniority.json", "seniorities")
    connection.executemany(
        """
        INSERT INTO DimSeniority (label, typical_min_exp, typical_max_exp)
        VALUES (?, ?, ?)
        ON CONFLICT(label) DO UPDATE SET
            typical_min_exp = excluded.typical_min_exp,
            typical_max_exp = excluded.typical_max_exp
        """,
        [
            (
                seniority["label"],
                seniority["typical_min_exp"],
                seniority["typical_max_exp"],
            )
            for seniority in seniorities
        ],
    )

    return len(seniorities)


def _load_roles_data(connection: sqlite3.Connection) -> int:
    """
    Load the roles data into the DimRole table.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
    """
    roles = load_seed("roles.json", "roles")
    # DO NOTHING rather than DO UPDATE: the name is the whole row, so a
    # conflict means the row is already exactly what the seed says. Reinserting
    # would only burn a new id, and FactJob.role_id points at the old one.
    connection.executemany(
        "INSERT INTO DimRole (role_name) VALUES (?) ON CONFLICT(role_name) DO NOTHING",
        [(role["name"],) for role in roles],
    )

    return len(roles)


def _load_degrees_data(connection: sqlite3.Connection) -> int:
    """
    Load the degrees data into the DimDegree table.

    Only name and field: 'level' has a column but no seed value, since it
    describes an instance of education rather than the canonical program.
    DO UPDATE on field like DimSeniority does on its years, because the name is
    the identity and re-bucketing a field in the seed should reach a base that
    already holds the degree.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
    """
    degrees = load_seed("degrees.json", "degrees")
    connection.executemany(
        """
        INSERT INTO DimDegree (name, field)
        VALUES (?, ?)
        ON CONFLICT(name) DO UPDATE SET field = excluded.field
        """,
        [(degree["name"], degree["field"]) for degree in degrees],
    )

    return len(degrees)


def _load_technologies_data(connection: sqlite3.Connection) -> int:
    """
    Load the technologies data into the DimTechnologies table.

    Only the canonical names. 'aliases' has no table on purpose, and 'parents'
    is a second pass: TechnologyDependency needs every technology inserted
    first, since react names javascript before the seed reaches it.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
    """
    technologies = load_seed("technologies.json", "technologies")
    connection.executemany(
        "INSERT INTO DimTechnologies (name) VALUES (?) ON CONFLICT(name) DO NOTHING",
        [(technology["name"],) for technology in technologies],
    )

    return len(technologies)


def _load_concepts_data(connection: sqlite3.Connection) -> int:
    """
    Load the concepts data into the DimConcepts table.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
    """
    concepts = load_seed("concepts.json", "concepts")
    connection.executemany(
        """
        INSERT INTO DimConcepts (concept_name)
        VALUES (?)
        ON CONFLICT(concept_name) DO NOTHING
        """,
        [(concept["name"],) for concept in concepts],
    )

    return len(concepts)


def run_db_creation():
    """
    Run the database creation process, including creating the schema and any necessary initial data.

    Idempotent from end to end: schema.sql creates only what is missing and
    every insert resolves its conflict, so this is safe to run on a base that
    already holds scraped jobs. Nothing is ever deleted, since a name dropped
    from a seed may still be referenced by a FactJob row.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_PATH)
    try:
        # Off by default in sqlite, and it stays per-connection: the loader in
        # etl/ has to turn it on again for the bridges to be checked at all.
        connection.execute("PRAGMA foreign_keys = ON")

        _create_schema(connection)
        seeded = {
            "DimSeniority": _load_seniority_data(connection),
            "DimRole": _load_roles_data(connection),
            "DimDegree": _load_degrees_data(connection),
            "DimTechnologies": _load_technologies_data(connection),
            "DimConcepts": _load_concepts_data(connection),
        }

        connection.commit()
    finally:
        # sqlite3.connect as a context manager commits but never closes, which
        # is why this is a try/finally instead.
        connection.close()

    print(f"Database ready at {DB_PATH}.")
    for table, count in seeded.items():
        print(f"  {table}: {count} seed entries")


if __name__ == "__main__":
    run_db_creation()
