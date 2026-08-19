"""Read candidate evidence and job requirements from the database.

This module deliberately stops before matching or scoring.  It turns the
normalized bridge tables into structures that the later matching stage can
compare without issuing one query per project or requirement.
"""

from datetime import date

import sqlite3
from collections import defaultdict, deque

from job_matcher.models import EvidenceTag, ProjectEvidence


def _minimum_depths(
    initial_depths: dict, edges: list[tuple]
) -> dict:
    """
    Walk child-to-parent edges and keep the shortest discovered depth.

    Args:
        initial_depths (dict): Root ids and their starting depths.
        edges (list[tuple]): Child id and parent id pairs.

    Returns:
        dict: Every reachable id mapped to its minimum depth.
    """
    parents_by_child = defaultdict(set)
    for child_id, parent_id in edges:
        parents_by_child[child_id].add(parent_id)

    depths = dict(initial_depths)
    queue = deque(initial_depths)

    while queue:
        child_id = queue.popleft()
        child_depth = depths[child_id]

        for parent_id in parents_by_child[child_id]:
            candidate_depth = child_depth + 1
            if candidate_depth >= depths.get(parent_id, float("inf")):
                continue

            depths[parent_id] = candidate_depth
            queue.append(parent_id)

    return depths


def _group_project_tags(
    rows: list[tuple],
) -> dict:
    """
    Group a project-to-dimension query into project id sets.

    Args:
        rows (list[tuple]): Project id and dimension id pairs.

    Returns:
        dict: Dimension ids grouped by project id.
    """
    grouped = defaultdict(set)
    for project_id, dimension_id in rows:
        grouped[project_id].add(dimension_id)
    return grouped


def get_project_evidence(
    connection: sqlite3.Connection,
    user_id: int,
) -> list[ProjectEvidence]:
    """Retrieve every project and its direct and inferred evidence.

    Technology and concept dependency edges point from child to parent.  A
    directly tagged technology or concept starts at depth zero.  Technology
    concepts start one level below the technology that implies them, after
    which concept dependencies are walked normally.

    Projects are not filtered for having tags: an untagged project is still
    returned so the caller can decide whether its other details matter later.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
        user_id (int): The candidate whose projects should be retrieved.

    Returns:
        list[ProjectEvidence]: One evidence record per project owned by the user.
    """
    projects = connection.execute(
        """
        SELECT id, experience_id
        FROM Project
        WHERE user_id = ?
        ORDER BY id
        """,
        (user_id,),
    ).fetchall()

    project_technologies = _group_project_tags(
        connection.execute(
            """
            SELECT pt.project_id, pt.technology_id
            FROM ProjectTechnologies pt
            JOIN Project p ON p.id = pt.project_id
            WHERE p.user_id = ?
            """,
            (user_id,),
        )
    )
    project_concepts = _group_project_tags(
        connection.execute(
            """
            SELECT pc.project_id, pc.concept_id
            FROM ProjectConcepts pc
            JOIN Project p ON p.id = pc.project_id
            WHERE p.user_id = ?
            """,
            (user_id,),
        )
    )

    technology_dependencies = connection.execute(
        "SELECT child_id, parent_id FROM TechnologyDependency"
    ).fetchall()
    concept_dependencies = connection.execute(
        "SELECT child_id, parent_id FROM ConceptDependency"
    ).fetchall()

    concepts_by_technology = defaultdict(set)
    for technology_id, concept_id in connection.execute(
        "SELECT technology_id, concept_id FROM TechnologyConcept"
    ):
        concepts_by_technology[technology_id].add(concept_id)

    evidence = []
    for project_id, experience_id in projects:
        direct_technologies = {
            technology_id: 0
            for technology_id in project_technologies.get(project_id, ())
        }
        technology_depths = _minimum_depths(
            direct_technologies,
            technology_dependencies,
        )

        # A concept implied by a directly tagged technology starts at depth 1.
        # Concepts implied by an inherited technology are deeper still.
        concept_roots = {
            concept_id: 0
            for concept_id in project_concepts.get(project_id, ())
        }
        for technology_id, technology_depth in technology_depths.items():
            for concept_id in concepts_by_technology[technology_id]:
                concept_depth = technology_depth + 1
                if concept_depth < concept_roots.get(concept_id, float("inf")):
                    concept_roots[concept_id] = concept_depth

        concept_depths = _minimum_depths(concept_roots, concept_dependencies)

        evidence.append(
            ProjectEvidence(
                id=project_id,
                experience_id=experience_id,
                technologies=[
                    EvidenceTag(id=technology_id, depth=depth)
                    for technology_id, depth in sorted(technology_depths.items())
                ],
                concepts=[
                    EvidenceTag(id=concept_id, depth=depth)
                    for concept_id, depth in sorted(concept_depths.items())
                ],
            )
        )

    return evidence


def get_experiences(connection: sqlite3.Connection, user_id: int) -> list[dict]:
    """Retrieve the candidate's work-history rows.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
        user_id (int): The candidate whose experience should be retrieved.

    Returns:
        list[dict]: Work history ordered by experience id.
    """
    rows = connection.execute(
        """
        SELECT
            fe.id,
            fe.company_id,
            dc.company_name,
            fe.role_id,
            dr.role_name,
            fe.seniority_id,
            ds.label,
            fe.start_date,
            fe.end_date,
            fe.day_to_day
        FROM FactExperience fe
        LEFT JOIN DimCompany dc ON dc.id = fe.company_id
        LEFT JOIN DimRole dr ON dr.id = fe.role_id
        LEFT JOIN DimSeniority ds ON ds.id = fe.seniority_id
        WHERE fe.user_id = ?
        ORDER BY fe.id
        """,
        (user_id,),
    ).fetchall()

    return [
        {
            "id": experience_id,
            "company_id": company_id,
            "role_id": role_id,
            "seniority_id": seniority_id,
            "seniority_label": seniority_label,
            "start_date": start_date,
            "end_date": date.today().isoformat() if end_date is None else end_date,
            "day_to_day": day_to_day,
        }
        for (
            experience_id,
            company_id,
            role_id,
            seniority_id,
            seniority_label,
            start_date,
            end_date,
            day_to_day,
        ) in rows
    ]


def _requirements_by_kind(
    rows: list[tuple],
) -> dict:
    """
    Split requirement rows into required and optional lists.

    Args:
        rows (list[tuple]): Dimension id,
            required flag, minimum experience, and maximum experience.

    Returns:
        dict: Required and optional rows.
    """
    requirements = {
        "required": [],
        "optional": [],
    }

    for dimension_id, required, min_exp, max_exp in rows:
        requirements["required" if required else "optional"].append(
            {
                "id": dimension_id,
                "min_exp": min_exp,
                "max_exp": max_exp,
            }
        )

    for values in requirements.values():
        values.sort(key=lambda value: value["id"])

    return requirements


def get_jobs(connection: sqlite3.Connection) -> list[dict]:
    """Retrieve job metadata and its required/optional requirements.

    This intentionally returns dictionaries rather than a job model: the job
    shape is still evolving, and this layer should expose the database facts
    without imposing scoring semantics on them.

    Args:
        connection (sqlite3.Connection): Open connection to the database.

    Returns:
        list[dict]: Job metadata and requirements, one dictionary per posting.
    """
    job_rows = connection.execute(
        """
        SELECT
            fj.id,
            fj.position_name,
            fj.company_id,
            dc.company_name,
            dr.role_name,
            fj.seniority_id,
            ds.label,
            ds.typical_min_exp,
            ds.typical_max_exp,
            fj.post_date,
            fj.source_url
        FROM FactJob fj
        LEFT JOIN DimCompany dc ON dc.id = fj.company_id
        LEFT JOIN DimRole dr ON dr.id = fj.role_id
        LEFT JOIN DimSeniority ds ON ds.id = fj.seniority_id
        ORDER BY fj.id
        """
    ).fetchall()

    technologies_by_job = defaultdict(list)
    for job_id, technology_id, required, min_exp, max_exp in connection.execute(
        """
        SELECT job_id, technology_id, required, min_exp, max_exp
        FROM JobTechnologies
        ORDER BY job_id, technology_id
        """
    ):
        technologies_by_job[job_id].append(
            {
                "id": technology_id,
                "required": required,
                "min_exp": min_exp,
                "max_exp": max_exp,
            }
        )

    concepts_by_job = defaultdict(list)
    for job_id, concept_id, required, min_exp, max_exp in connection.execute(
        """
        SELECT job_id, concept_id, required, min_exp, max_exp
        FROM JobConcepts
        ORDER BY job_id, concept_id
        """
    ):
        concepts_by_job[job_id].append(
            {
                "id": concept_id,
                "required": required,
                "min_exp": min_exp,
                "max_exp": max_exp,
            }
        )

    degrees_by_job = defaultdict(list)
    for job_id, degree_id in connection.execute(
        "SELECT job_id, degree_id FROM JobDegrees ORDER BY job_id, degree_id"
    ):
        degrees_by_job[job_id].append(degree_id)

    jobs = []
    for row in job_rows:
        (
            job_id,
            position_name,
            company_id,
            company_name,
            role_name,
            seniority_id,
            seniority_label,
            typical_min_exp,
            typical_max_exp,
            post_date,
            source_url,
        ) = row

        jobs.append(
            {
                "id": job_id,
                "position_name": position_name,
                "company_id": company_id,
                "company_name": company_name,
                "role_name": role_name,
                "seniority_id": seniority_id,
                "seniority_label": seniority_label,
                "typical_min_exp": typical_min_exp,
                "typical_max_exp": typical_max_exp,
                "post_date": post_date,
                "source_url": source_url,
                "technologies": _requirements_by_kind(
                    (
                        requirement["id"],
                        requirement["required"],
                        requirement["min_exp"],
                        requirement["max_exp"],
                    )
                    for requirement in technologies_by_job.get(job_id, [])
                ),
                "concepts": _requirements_by_kind(
                    (
                        requirement["id"],
                        requirement["required"],
                        requirement["min_exp"],
                        requirement["max_exp"],
                    )
                    for requirement in concepts_by_job.get(job_id, [])
                ),
                "degree_ids": degrees_by_job.get(job_id, []),
            }
        )

    return jobs
