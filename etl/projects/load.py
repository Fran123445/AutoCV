import sqlite3

# The dimensions are shared with the job side and seeded once, so the lookups
# are too rather than written twice.
from etl.jobs.load import (
    UnknownSeedValue,
    _solve_concept_name_id as solve_concept_name_id,
    _solve_technology_name_id as solve_technology_name_id,
)


# Multiuser schema, one user in practice. The row carries nothing but a
# birth_date nobody fills, so it is created on demand instead of seeded.
DEFAULT_USER_ID = 1


def _solve_user_id(connection: sqlite3.Connection, user_id: int) -> int:
    """
    Makes sure the user the project hangs off exists.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
        user_id (int): The user the projects belong to.

    Returns:
        int: The same id, now guaranteed to satisfy the foreign key.
    """
    connection.execute(
        "INSERT INTO FactUser (id) VALUES (?) ON CONFLICT(id) DO NOTHING",
        (user_id,),
    )

    return user_id


def _descriptions_by_name(descriptions: dict, kind: str) -> dict[str, str | None]:
    """
    Index one kind of description by the name it describes.

    Args:
        descriptions (dict): The describer's output. Missing a key entirely when
            that kind had nothing to describe.
        kind (str): 'technologies' or 'concepts'.

    Returns:
        dict[str, str | None]: Canonical name to its phrase, or to None.
    """
    return {entry["name"]: entry["descr"] for entry in descriptions.get(kind, [])}


def _load_bridge(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    project_id: int,
    entries: list[tuple[int, str | None]],
):
    """
    Insert one project's rows into ProjectTechnologies or ProjectConcepts.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
        table (str): Bridge table name.
        column (str): Column holding the dimension id on that table.
        project_id (int): Project id the rows hang off.
        entries (list[tuple[int, str | None]]): Dimension id and its phrase.
    """
    connection.executemany(
        f"""
        INSERT INTO {table} (project_id, {column}, descr)
        VALUES (?, ?, ?)
        ON CONFLICT(project_id, {column}) DO NOTHING
        """,
        [(project_id, dimension_id, descr) for dimension_id, descr in entries],
    )


def load(
    transformed_data: dict,
    connection: sqlite3.Connection,
    user_id: int = DEFAULT_USER_ID,
) -> int | None:
    """
    Loads the transformed project into the database.

    One project, one transaction: either the Project row and both bridges land
    or none of them do. A project already in the base is skipped rather than
    rewritten, deduping on source_path the way the job side does on
    linkedin_job_id. experience_id is left null, which is what marks a project
    as personal.

    Args:
        transformed_data (dict): The data to load, as etl.projects.transform
            produced it.
        connection (sqlite3.Connection): Open connection to the database.
        user_id (int): The user the project belongs to.

    Returns:
        int | None: The Project id, or None when it was already there.

    Raises:
        UnknownSeedValue: A canonical name has no row in its dimension.
    """
    technologies = transformed_data["technologies"]["technologies"]
    narrative = transformed_data["narrative"]
    descriptions = transformed_data["descriptions"]

    with connection:
        cursor = connection.execute(
            """
            INSERT INTO Project (user_id, task_desc, source_path)
            VALUES (?, ?, ?)
            ON CONFLICT(source_path) DO NOTHING
            """,
            (
                _solve_user_id(connection, user_id),
                narrative["task_desc"],
                transformed_data["path"],
            ),
        )

        # Nothing inserted means the conflict fired and the project is already
        # loaded. lastrowid would be stale, so bail before touching the bridges.
        if cursor.rowcount == 0:
            return None

        project_id = cursor.lastrowid

        technology_descriptions = _descriptions_by_name(descriptions, "technologies")
        _load_bridge(
            connection,
            "ProjectTechnologies",
            "technology_id",
            project_id,
            [
                (
                    solve_technology_name_id(connection, name),
                    technology_descriptions.get(name),
                )
                for name in technologies
            ],
        )

        concept_descriptions = _descriptions_by_name(descriptions, "concepts")
        _load_bridge(
            connection,
            "ProjectConcepts",
            "concept_id",
            project_id,
            [
                (
                    solve_concept_name_id(connection, name),
                    concept_descriptions.get(name),
                )
                for name in narrative["concepts"]
            ],
        )

    return project_id
