import json
import sqlite3
from collections.abc import Iterable

from job_matcher.models import JobPosting


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


def _split_by_required(
    rows: Iterable[tuple[int, int, int]],
) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
    """
    Group tagged ids by job, keeping the required ones apart from the optional.

    Args:
        rows (Iterable[tuple[int, int, int]]): (job_id, tagged_id, required)
            triples, as JobTechnologies and JobConcepts both store them.

    Returns:
        tuple[dict[int, set[int]], dict[int, set[int]]]: The required ids by job
            and the optional ids by job. Jobs with nothing tagged are absent
            from both.
    """
    required_by_job: dict[int, set[int]] = {}
    optional_by_job: dict[int, set[int]] = {}

    for job_id, tagged_id, required in rows:
        bucket = required_by_job if required else optional_by_job
        bucket.setdefault(job_id, set()).add(tagged_id)

    return required_by_job, optional_by_job


def _get_job_data(connection: sqlite3.Connection) -> list[JobPosting]:
    """
    Every job with its required and optional tech/concept ids folded into sets.

    Three flat queries and a regroup in Python, not one query per job: the
    tagging tables are small enough to read whole, and the alternative is a
    round trip per posting for rows that are mostly already in the page cache.

    Args:
        connection (sqlite3.Connection): Open connection to the database.

    Returns:
        list[JobPosting]: One posting per row of FactJob.
    """
    job_list = connection.execute(
        """
        SELECT
            fj.id,
            dc.company_name,
            fj.position_name,
            ds.typical_min_exp
        FROM FactJob fj LEFT JOIN DimCompany dc ON
            fj.company_id = dc.id
        LEFT JOIN DimSeniority ds ON
            fj.seniority_id = ds.id
        """
    )

    required_techs_by_job, optional_techs_by_job = _split_by_required(
        connection.execute(
            """
            SELECT job_id, technology_id, required
            FROM JobTechnologies
            """
        )
    )

    required_concepts_by_job, optional_concepts_by_job = _split_by_required(
        connection.execute(
            """
            SELECT job_id, concept_id, required
            FROM JobConcepts
            """
        )
    )

    return [
        JobPosting(
            id=job_id,
            company_name=company_name,
            position_name=position_name,
            typical_min_exp=typical_min_exp,
            required_technology_ids=required_techs_by_job.get(job_id, set()),
            optional_technology_ids=optional_techs_by_job.get(job_id, set()),
            required_concept_ids=required_concepts_by_job.get(job_id, set()),
            optional_concept_ids=optional_concepts_by_job.get(job_id, set()),
        )
        for job_id, company_name, position_name, typical_min_exp in job_list
    ]


def match_jobs_for_user(user_id: int):
    pass