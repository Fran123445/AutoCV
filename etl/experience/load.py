import sqlite3

from etl.candidate import (
    DEFAULT_USER_ID,
    descriptions_by_name,
    load_project_bridge,
    load_user_bridge,
)
from etl.dims import (
    solve_company_name_id,
    solve_concept_name_id,
    solve_degree_id,
    solve_role_id,
    solve_seniority_id,
    solve_technology_name_id,
)


class MissingProjectStory(Exception):
    """
    A project block reached the load stage with nothing written in it.

    Project.task_desc is NOT NULL and the transform stage keeps the block rather
    than dropping it, precisely so the empty one is refused here instead of
    disappearing between the file and the base. The fix is in experience.toml:
    write the story or delete the block.
    """


def _load_profile(connection: sqlite3.Connection, profile: dict, user_id: int) -> int:
    """
    Write the candidate's own row and their links.

    Updated on conflict rather than skipped, unlike everything else the ETL
    loads: there is one user row and the file is its only source, so a re-run
    after fixing a phone number has to reach the base. Nothing downstream edits
    these columns by hand the way FactJob.status is edited, so there is nothing
    to walk back.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
        profile (dict): The profile block, as etl.experience.transform left it.
        user_id (int): The user being loaded.

    Returns:
        int: The same id, now guaranteed to satisfy the foreign keys.
    """
    connection.execute(
        """
        INSERT INTO FactUser (id, full_name, email, phone, location, birth_date)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            full_name = excluded.full_name,
            email = excluded.email,
            phone = excluded.phone,
            location = excluded.location,
            birth_date = excluded.birth_date
        """,
        (
            user_id,
            profile["full_name"],
            profile["email"],
            profile["phone"],
            profile["location"],
            profile["birth_date"],
        ),
    )

    connection.executemany(
        """
        INSERT INTO UserLink (user_id, kind, url)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, kind) DO UPDATE SET url = excluded.url
        """,
        [
            (user_id, link["kind"], link["url"])
            for link in profile["links"]
            # Both columns are NOT NULL, and the template ships the kinds with
            # their urls blank: a half-filled link is a line the candidate has
            # not written yet, not a row.
            if link["kind"] is not None and link["url"] is not None
        ],
    )

    return user_id


def _load_education(connection: sqlite3.Connection, education: list[dict], user_id: int):
    """
    Write the education blocks.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
        education (list[dict]): The education blocks, transformed.
        user_id (int): The user they belong to.

    Raises:
        UnknownSeedValue: A degree name has no row in DimDegree.
    """
    connection.executemany(
        # Dates update on conflict for the same reason the profile does: a
        # degree finished since the last run is an edit to the file, not a new
        # block. A block with no institution re-inserts instead, since the
        # primary key covers that column and nulls do not conflict in sqlite;
        # defaulting it to '' would be worse, collapsing two schools into one.
        """
        INSERT INTO UserEducation (user_id, degree_id, institution, gpa, start_date, end_date)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, degree_id, institution) DO UPDATE SET
            gpa = excluded.gpa,
            start_date = excluded.start_date,
            end_date = excluded.end_date
        """,
        [
            (
                user_id,
                solve_degree_id(connection, block["degree"]),
                block["institution"],
                block["gpa"],
                block["start_date"],
                block["end_date"],
            )
            for block in education
        ],
    )


def _load_language(connection: sqlite3.Connection, languages: list[dict], user_id: int):
    """
    Write the spoken languages.

    Level updates on conflict, like the profile and the education dates: a
    language whose level moved is an edit to the file, not a second language.
    Dropping one from the file leaves its row behind, which is the same bargain
    the rest of the candidate side makes — nothing here deletes.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
        languages (list[dict]): The language blocks, transformed.
        user_id (int): The user they belong to.
    """
    connection.executemany(
        """
        INSERT INTO UserLanguage (user_id, name, level)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, name) DO UPDATE SET level = excluded.level
        """,
        [(user_id, language["name"], language["level"]) for language in languages],
    )


def _load_experience(
    connection: sqlite3.Connection, job: dict, user_id: int
) -> tuple[int, bool]:
    """
    Write one job block, replacing the row a previous run already wrote.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
        job (dict): One job block, transformed.
        user_id (int): The user whose history this is.

    Returns:
        tuple[int, bool]: The FactExperience id, and whether this source block
            was loaded. Existing rows are updated in place because the TOML is
            authoritative for the candidate's work history.

    Raises:
        UnknownSeedValue: A canonical name has no row in its dimension.
    """
    day_to_day = job["day_to_day"]

    connection.execute(
        """
        INSERT INTO FactExperience (
            user_id, source_id, company_id, role_id, job_title, seniority_id,
            start_date, end_date, day_to_day
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, source_id) DO UPDATE SET
            company_id = excluded.company_id,
            role_id = excluded.role_id,
            job_title = excluded.job_title,
            seniority_id = excluded.seniority_id,
            start_date = excluded.start_date,
            end_date = excluded.end_date,
            day_to_day = excluded.day_to_day
        """,
        (
            user_id,
            job["id"],
            solve_company_name_id(connection, job["company"]),
            solve_role_id(connection, job["role"]),
            job["title"],
            # No years to fall back on: the file states a label or states
            # nothing, and the job's own dates are not a claim about seniority.
            solve_seniority_id(connection, job["seniority"], None),
            job["start_date"],
            job["end_date"],
            None if day_to_day is None else day_to_day["narrative"]["day_to_day"],
        ),
    )

    row = connection.execute(
        "SELECT id FROM FactExperience WHERE user_id = ? AND source_id = ?",
        (user_id, job["id"]),
    ).fetchone()

    return row[0], True


def _load_project(
    connection: sqlite3.Connection, project: dict, experience_id: int, user_id: int
) -> int:
    """
    Write one project a candidate did at a job, with its two bridges.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
        project (dict): One project block, transformed.
        experience_id (int): The job it was done at.
        user_id (int): The user it belongs to. Denormalised onto Project the
            same way the personal ones carry it.

    Returns:
        int: The Project id, whether the project was inserted or updated.

    Raises:
        MissingProjectStory: The block has no story written in it.
        UnknownSeedValue: A canonical name has no row in its dimension.
    """
    identified = project["identified"]
    if identified is None:
        raise MissingProjectStory(f"project {project['id']!r} has no story")

    technologies = identified["technologies"]["technologies"]
    narrative = identified["narrative"]
    descriptions = identified["descriptions"]

    connection.execute(
        # source_path stays null: there is no repository behind this project,
        # which is also what tells it apart from one the projects pipeline
        # loaded. The file's id goes to source_id and dedupes it instead.
        """
        INSERT INTO Project (user_id, experience_id, source_id, task_desc)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(experience_id, source_id) DO UPDATE SET
            user_id = excluded.user_id,
            task_desc = excluded.task_desc
        """,
        (user_id, experience_id, project["id"], narrative["task_desc"]),
    )

    project_id = connection.execute(
        """
        SELECT id
        FROM Project
        WHERE experience_id = ? AND source_id = ?
        """,
        (experience_id, project["id"]),
    ).fetchone()[0]

    # Evidence is a complete snapshot, not an append-only history. Remove the
    # old bridges before loading the new technology/concept set and descriptions.
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
            (solve_concept_name_id(connection, name), concept_descriptions.get(name))
            for name in narrative["concepts"]
        ],
    )

    return project_id


def _delete_project(connection: sqlite3.Connection, project_id: int):
    """Delete an experience project and its evidence bridges."""
    connection.execute(
        "DELETE FROM ProjectTechnologies WHERE project_id = ?", (project_id,)
    )
    connection.execute(
        "DELETE FROM ProjectConcepts WHERE project_id = ?", (project_id,)
    )
    connection.execute("DELETE FROM Project WHERE id = ?", (project_id,))


def _delete_experience(connection: sqlite3.Connection, experience_id: int):
    """Delete an experience row and all projects/evidence hanging from it."""
    project_ids = connection.execute(
        "SELECT id FROM Project WHERE experience_id = ?", (experience_id,)
    ).fetchall()
    for (project_id,) in project_ids:
        _delete_project(connection, project_id)

    connection.execute("DELETE FROM FactExperience WHERE id = ?", (experience_id,))


def _rollup_names(jobs: list[dict]) -> tuple[list[str], list[str]]:
    """
    Gather every technology and concept the file claims for the candidate.

    The union of what the jobs and their projects named, since UserTechnologies
    and UserConcepts answer 'has this candidate touched X' and the bridges under
    each project already answer where.

    Args:
        jobs (list[dict]): The job blocks, transformed.

    Returns:
        tuple[list[str], list[str]]: Canonical technology names and concept
            names, deduped and sorted so a run writes them in a stable order.
    """
    technologies = set()
    concepts = set()

    for job in jobs:
        day_to_day = job["day_to_day"]
        if day_to_day is not None:
            technologies.update(day_to_day["technologies"]["technologies"])
            concepts.update(day_to_day["narrative"]["concepts"])

        for project in job["projects"]:
            identified = project["identified"]
            if identified is None:
                continue

            technologies.update(identified["technologies"]["technologies"])
            concepts.update(identified["narrative"]["concepts"])

    return sorted(technologies), sorted(concepts)


def _replace_user_rollups(
    connection: sqlite3.Connection, jobs: list[dict], user_id: int
):
    """Make candidate skill rollups match current experience plus personal projects."""
    technology_names, concept_names = _rollup_names(jobs)
    technology_ids = {
        solve_technology_name_id(connection, name) for name in technology_names
    }
    concept_ids = {
        solve_concept_name_id(connection, name) for name in concept_names
    }

    # Personal projects are maintained by the projects pipeline and remain
    # valid evidence when the experience source is replaced.
    technology_ids.update(
        row[0]
        for row in connection.execute(
            """
            SELECT DISTINCT pt.technology_id
            FROM ProjectTechnologies pt
            JOIN Project p ON p.id = pt.project_id
            WHERE p.user_id = ? AND p.experience_id IS NULL
            """,
            (user_id,),
        )
    )
    concept_ids.update(
        row[0]
        for row in connection.execute(
            """
            SELECT DISTINCT pc.concept_id
            FROM ProjectConcepts pc
            JOIN Project p ON p.id = pc.project_id
            WHERE p.user_id = ? AND p.experience_id IS NULL
            """,
            (user_id,),
        )
    )

    for table, column, ids in (
        ("UserTechnologies", "technology_id", technology_ids),
        ("UserConcepts", "concept_id", concept_ids),
    ):
        if ids:
            placeholders = ", ".join("?" for _ in ids)
            connection.execute(
                f"""
                DELETE FROM {table}
                WHERE user_id = ? AND {column} NOT IN ({placeholders})
                """,
                (user_id, *sorted(ids)),
            )
        else:
            connection.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))

        load_user_bridge(connection, table, column, user_id, sorted(ids))


def load(
    transformed_data: dict,
    connection: sqlite3.Connection,
    user_id: int = DEFAULT_USER_ID,
) -> dict:
    """
    Loads the transformed experience into the database.

    One file, one transaction, unlike the other two loaders, which take one unit
    at a time out of a directory: this stage has a single unit and it spans every
    table on the candidate's side. A half-loaded candidate is worse than none —
    a job whose projects did not land looks like a job somebody did nothing at.

    Args:
        transformed_data (dict): The data to load, as etl.experience.transform
            produced it.
        connection (sqlite3.Connection): Open connection to the database.
        user_id (int): The user the file describes.

    Returns:
        dict: What experience blocks were loaded. Existing jobs and projects
            count as loaded because they are overwritten in place. The
            profile, education and languages are not counted: they are written
            on every run.

    Raises:
        MissingProjectStory: A project block has no story written in it.
        UnknownSeedValue: A canonical name has no row in its dimension.
    """
    jobs = transformed_data["jobs"]
    counts = {
        "experiences_loaded": 0,
        "experiences_skipped": 0,
        "projects_loaded": 0,
        "projects_skipped": 0,
    }

    with connection:
        _load_profile(connection, transformed_data["profile"], user_id)
        _load_education(connection, transformed_data["education"], user_id)
        _load_language(connection, transformed_data["languages"], user_id)

        current_job_ids = {job["id"] for job in jobs}

        for job in jobs:
            experience_id, _loaded = _load_experience(connection, job, user_id)
            counts["experiences_loaded"] += 1

            current_project_ids = {project["id"] for project in job["projects"]}
            for project in job["projects"]:
                _load_project(connection, project, experience_id, user_id)
                counts["projects_loaded"] += 1

            stale_projects = connection.execute(
                """
                SELECT id, source_id
                FROM Project
                WHERE experience_id = ?
                """,
                (experience_id,),
            ).fetchall()
            for project_id, source_id in stale_projects:
                if source_id not in current_project_ids:
                    _delete_project(connection, project_id)

        # The TOML is the complete source of truth for experience rows. Remove
        # jobs that were deleted from it, including their project evidence.
        stale_experiences = connection.execute(
            """
            SELECT id, source_id
            FROM FactExperience
            WHERE user_id = ? AND source_id IS NOT NULL
            """,
            (user_id,),
        ).fetchall()
        for experience_id, source_id in stale_experiences:
            if source_id not in current_job_ids:
                _delete_experience(connection, experience_id)

        # Rebuild aggregate skill claims so tags removed from the TOML do not
        # survive. Personal-project evidence is preserved separately.
        _replace_user_rollups(connection, jobs, user_id)

    return counts
