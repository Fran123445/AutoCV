import sqlite3

# The dimensions are shared with the other two pipelines and seeded once, so the
# lookups are too rather than written a third time. The project bridges come from
# the projects side for the same reason: a project born of a job writes the same
# two tables with the same columns as one read off a repository.
from etl.jobs.load import (
    UnknownSeedValue,
    _solve_company_name_id as solve_company_name_id,
    _solve_concept_name_id as solve_concept_name_id,
    _solve_degree_id as solve_degree_id,
    _solve_role_id as solve_role_id,
    _solve_seniority_id as solve_seniority_id,
    _solve_technology_name_id as solve_technology_name_id,
)
from etl.projects.load import (
    DEFAULT_USER_ID,
    _descriptions_by_name as descriptions_by_name,
    _load_bridge as load_project_bridge,
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
        INSERT INTO UserEducation (user_id, degree_id, institution, start_date, end_date)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, degree_id, institution) DO UPDATE SET
            start_date = excluded.start_date,
            end_date = excluded.end_date
        """,
        [
            (
                user_id,
                solve_degree_id(connection, block["degree"]),
                block["institution"],
                block["start_date"],
                block["end_date"],
            )
            for block in education
        ],
    )


def _load_experience(
    connection: sqlite3.Connection, job: dict, user_id: int
) -> tuple[int, bool]:
    """
    Write one job block, or find the row a previous run already wrote.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
        job (dict): One job block, transformed.
        user_id (int): The user whose history this is.

    Returns:
        tuple[int, bool]: The FactExperience id, and whether this run inserted
            it. A job already in the base still returns its id: its projects are
            deduped one by one, so a block added to a job loaded last week lands
            without the job itself being touched.

    Raises:
        UnknownSeedValue: A canonical name has no row in its dimension.
    """
    day_to_day = job["day_to_day"]

    cursor = connection.execute(
        """
        INSERT INTO FactExperience (
            user_id, source_id, company_id, role_id, seniority_id, start_date,
            end_date, day_to_day
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, source_id) DO NOTHING
        """,
        (
            user_id,
            job["id"],
            solve_company_name_id(connection, job["company"]),
            solve_role_id(connection, job["role"]),
            # No years to fall back on: the file states a label or states
            # nothing, and the job's own dates are not a claim about seniority.
            solve_seniority_id(connection, job["seniority"], None),
            job["start_date"],
            job["end_date"],
            None if day_to_day is None else day_to_day["narrative"]["day_to_day"],
        ),
    )

    if cursor.rowcount == 0:
        row = connection.execute(
            "SELECT id FROM FactExperience WHERE user_id = ? AND source_id = ?",
            (user_id, job["id"]),
        ).fetchone()

        return row[0], False

    return cursor.lastrowid, True


def _load_project(
    connection: sqlite3.Connection, project: dict, experience_id: int, user_id: int
) -> int | None:
    """
    Write one project a candidate did at a job, with its two bridges.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
        project (dict): One project block, transformed.
        experience_id (int): The job it was done at.
        user_id (int): The user it belongs to. Denormalised onto Project the
            same way the personal ones carry it.

    Returns:
        int | None: The Project id, or None when it was already there.

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

    cursor = connection.execute(
        # source_path stays null: there is no repository behind this project,
        # which is also what tells it apart from one the projects pipeline
        # loaded. The file's id goes to source_id and dedupes it instead.
        """
        INSERT INTO Project (user_id, experience_id, source_id, task_desc)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(experience_id, source_id) DO NOTHING
        """,
        (user_id, experience_id, project["id"], narrative["task_desc"]),
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
            (solve_concept_name_id(connection, name), concept_descriptions.get(name))
            for name in narrative["concepts"]
        ],
    )

    return project_id


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


def _load_user_bridge(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    user_id: int,
    dimension_ids: list[int],
):
    """
    Insert the rollup rows into UserTechnologies or UserConcepts.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
        table (str): Bridge table name.
        column (str): Column holding the dimension id on that table.
        user_id (int): The user the rows hang off.
        dimension_ids (list[int]): Resolved ids, already deduped.
    """
    connection.executemany(
        # proficiency is left null and never overwritten: the schema calls it
        # the candidate's own claim about their level, and the file makes no
        # such claim. A value set by hand in the base survives a re-run.
        f"""
        INSERT INTO {table} (user_id, {column}, proficiency)
        VALUES (?, ?, NULL)
        ON CONFLICT(user_id, {column}) DO NOTHING
        """,
        [(user_id, dimension_id) for dimension_id in dimension_ids],
    )


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
        dict: What landed and what was already there, by kind. The profile and
            the education are not counted: they are written on every run.

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

        for job in jobs:
            experience_id, inserted = _load_experience(connection, job, user_id)
            counts["experiences_loaded" if inserted else "experiences_skipped"] += 1

            for project in job["projects"]:
                project_id = _load_project(connection, project, experience_id, user_id)
                counts["projects_loaded" if project_id else "projects_skipped"] += 1

        technologies, concepts = _rollup_names(jobs)
        _load_user_bridge(
            connection,
            "UserTechnologies",
            "technology_id",
            user_id,
            [solve_technology_name_id(connection, name) for name in technologies],
        )
        _load_user_bridge(
            connection,
            "UserConcepts",
            "concept_id",
            user_id,
            [solve_concept_name_id(connection, name) for name in concepts],
        )

    return counts
