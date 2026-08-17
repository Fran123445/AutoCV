import json
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

def _get_user_concepts(
    connection: sqlite3.Connection, user_id: int, technologies: set[int]
) -> set[int]:
    """
    Every concept the candidate can claim, from three places at once. 
    What a tagger named, what the technologies imply, and what either of those
    implies up ConceptDependency.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
        user_id (int): The candidate.
        technologies (set[int]): DimTechnologies ids, as _get_user_techs left them.

    Returns:
        set[int]: DimConcepts ids.
    """
    rows = connection.execute(
        # json_each and not a built IN list: the set is empty for a candidate
        # with nothing tagged yet, and 'IN ()' does not parse.
        """
        WITH RECURSIVE closure(concept_id) AS (
            SELECT concept_id FROM UserConcepts WHERE user_id = ?

            UNION
            
            SELECT bridge.concept_id
            FROM TechnologyConcept bridge
            JOIN json_each(?) technology ON technology.value = bridge.technology_id
            
            UNION
            
            SELECT dependency.parent_id
            FROM ConceptDependency dependency
            JOIN closure ON closure.concept_id = dependency.child_id
        )
        SELECT concept_id FROM closure
        """,
        (user_id, json.dumps(sorted(technologies))),
    )

    return {row[0] for row in rows}

def _get_full_job_data():
    pass

def match_jobs_for_user(user_id: int):
    pass