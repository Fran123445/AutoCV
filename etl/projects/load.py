import sqlite3

from etl.candidate import (
    DEFAULT_USER_ID,
    descriptions_by_name,
    load_project_bridge,
    load_user_bridge,
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
    or none of them do. A project already in the base is updated in place,
    deduping on source_path while keeping the existing Project id. Its evidence
    bridges are replaced so tags and descriptions removed from the new
    transform do not survive the reload. experience_id is left null, which is
    what marks a project as personal.

    The rollup into the user bridges runs on every load. Those rows describe
    the candidate's aggregate experience and may also be supported by another
    project or the experience pipeline, so reloading one project must not
    remove them. Re-inserting them resolves the existing conflict harmlessly.

    Args:
        transformed_data (dict): The data to load, as etl.projects.transform
            produced it.
        connection (sqlite3.Connection): Open connection to the database.
        user_id (int): The user the project belongs to.

    Returns:
        int: The Project id, whether the project was inserted or updated.

    Raises:
        UnknownSeedValue: A canonical name has no row in its dimension.
    """
    technologies = transformed_data["technologies"]["technologies"]
    narrative = transformed_data["narrative"]
    descriptions = transformed_data["descriptions"]

    with connection:
        solve_user_id(connection, user_id)

        technology_ids = [
            solve_technology_name_id(connection, name) for name in technologies
        ]
        concept_ids = [
            solve_concept_name_id(connection, name) for name in narrative["concepts"]
        ]
        load_user_bridge(
            connection, "UserTechnologies", "technology_id", user_id, technology_ids
        )
        load_user_bridge(
            connection, "UserConcepts", "concept_id", user_id, concept_ids
        )

        connection.execute(
            """
            INSERT INTO Project (
                user_id, task_desc, source_path, head_commit,
                first_commit_at, last_commit_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_path) DO UPDATE SET
                user_id = excluded.user_id,
                experience_id = excluded.experience_id,
                task_desc = excluded.task_desc,
                source_id = excluded.source_id,
                head_commit = excluded.head_commit,
                first_commit_at = excluded.first_commit_at,
                last_commit_at = excluded.last_commit_at
            """,
            (
                user_id,
                narrative["task_desc"],
                transformed_data["path"],
                transformed_data.get("head_commit"),
                transformed_data.get("first_commit_at"),
                transformed_data.get("last_commit_at"),
            ),
        )

        # lastrowid is stale when the conflict path updates an existing row, so
        # resolve the id by the natural key after either insert or update.
        project_id = connection.execute(
            "SELECT id FROM Project WHERE source_path = ?",
            (transformed_data["path"],),
        ).fetchone()[0]

        # The bridge rows are the complete evidence for this project, not an
        # append-only history. Delete first so tags or descriptions removed by
        # the new transform cannot remain attached to the old project state.
        connection.execute(
            "DELETE FROM ProjectTechnologies WHERE project_id = ?", (project_id,)
        )
        connection.execute(
            "DELETE FROM ProjectConcepts WHERE project_id = ?", (project_id,)
        )

        technology_descriptions = descriptions_by_name(descriptions, "technologies")
        load_project_bridge(
            connection,
            "ProjectTechnologies",
            "technology_id",
            project_id,
            [
                (technology_id, technology_descriptions.get(name))
                for name, technology_id in zip(technologies, technology_ids)
            ],
        )

        concept_descriptions = descriptions_by_name(descriptions, "concepts")
        load_project_bridge(
            connection,
            "ProjectConcepts",
            "concept_id",
            project_id,
            [
                (concept_id, concept_descriptions.get(name))
                for name, concept_id in zip(narrative["concepts"], concept_ids)
            ],
        )

    return project_id
