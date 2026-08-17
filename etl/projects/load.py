import sqlite3

from etl.candidate import (
    DEFAULT_USER_ID,
    descriptions_by_name,
    load_project_bridge,
    solve_user_id,
)
from etl.dims import solve_concept_name_id, solve_technology_name_id


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
                solve_user_id(connection, user_id),
                narrative["task_desc"],
                transformed_data["path"],
            ),
        )

        # Nothing inserted means the conflict fired and the project is already
        # loaded. lastrowid would be stale, so bail before touching the bridges.
        if cursor.rowcount == 0:
            return None

        project_id = cursor.lastrowid

        technology_descriptions = descriptions_by_name(descriptions, "technologies")
        load_project_bridge(
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

        concept_descriptions = descriptions_by_name(descriptions, "concepts")
        load_project_bridge(
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
