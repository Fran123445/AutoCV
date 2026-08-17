"""
The rows on the candidate's side of the base that two pipelines both write.

A Project comes from either of two places: a repository the projects pipeline
walked, or a story the candidate told about a job. What is written is the same
row and the same two bridges either way — only the dedupe key and the
experience_id differ — so the writing lives here and each loader keeps what is
its own. The job side never touches these tables.
"""

import sqlite3


# Multiuser schema, one user in practice. The row carries nothing but a
# birth_date nobody fills, so it is created on demand instead of seeded.
DEFAULT_USER_ID = 1


def solve_user_id(connection: sqlite3.Connection, user_id: int) -> int:
    """
    Makes sure the user the project hangs off exists.

    For the pipelines that write a project without knowing anything about the
    candidate. The experience pipeline has the profile block in hand and writes
    the columns instead of an empty row.

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


def descriptions_by_name(descriptions: dict, kind: str) -> dict[str, str | None]:
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


def load_project_bridge(
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


def load_user_bridge(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    user_id: int,
    dimension_ids: list[int],
):
    """
    Insert the rollup rows into UserTechnologies or UserConcepts.

    Shared for the same reason the project bridge is: a tag reaches the
    candidate from a repository the projects pipeline walked or from a story
    the experience file tells, and either way it is the same claim. The schema
    wants a project's tags contained in the user's, so every loader that writes
    a project bridge writes this one too.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
        table (str): Bridge table name.
        column (str): Column holding the dimension id on that table.
        user_id (int): The user the rows hang off.
        dimension_ids (list[int]): Resolved ids, already deduped.
    """
    connection.executemany(
        # proficiency is left null and never overwritten: the schema calls it
        # the candidate's own claim about their level, and neither pipeline
        # makes such a claim. A value set by hand in the base survives a re-run.
        f"""
        INSERT INTO {table} (user_id, {column}, proficiency)
        VALUES (?, ?, NULL)
        ON CONFLICT(user_id, {column}) DO NOTHING
        """,
        [(user_id, dimension_id) for dimension_id in dimension_ids],
    )
