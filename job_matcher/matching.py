import sqlite3


def _get_user_techs(connection: sqlite3.Connection, user_id: int) -> set[int]:
    """
    Every technology the candidate can claim, tagged ones and implied ones.

    UserTechnologies only holds what a tagger named. A posting asking for
    'javascript' from someone who declared 'react' has to match, so the walk up
    TechnologyDependency belongs here and not in the caller.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
        user_id (int): The candidate.

    Returns:
        set[int]: DimTechnologies ids.
    """
    rows = connection.execute(
        """
        WITH RECURSIVE closure(technology_id) AS (
            SELECT technology_id FROM UserTechnologies WHERE user_id = ?
            UNION
            SELECT dependency.parent_id
            FROM TechnologyDependency dependency
            JOIN closure ON closure.technology_id = dependency.child_id
        )
        SELECT technology_id FROM closure
        """,
        (user_id,),
    )

    return {row[0] for row in rows}

def _get_user_concepts(user_id: int, technologies: set[int]):
    pass

def _get_full_job_data():
    pass

def match_jobs_for_user(user_id: int):
    pass