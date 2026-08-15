from datetime import date, timedelta

import sqlite3


class UnknownSeedValue(Exception):
    """
    A canonical name reached the load stage without a row in its dimension.

    Never a posting's fault. Constrained decoding means the identifiers can
    only ever emit names from the registries, so this fires when the base was
    seeded from an older seeds/ than the one that produced the transform
    output. Re-running db_creation.py is the fix.
    """


# Only two of the three modalities say anything about days on site. "Híbrido"
# is a word, not a count: the posting says you come in sometimes and never says
# how often, so it loads as null like a posting that stays quiet. Losing the
# distinction is deliberate, since the column measures days rather than naming
# an arrangement.
_MODALITY_DAYS = {
    "En remoto": 0,
    "Presencial": 5,
    "Híbrido": None,
}


def _solve_company_name_id(connection: sqlite3.Connection, company_name: str | None) -> int | None:
    """
    Solves the company name to its corresponding ID.

    The one dimension with no seed: companies arrive with the postings, so a
    name that is missing gets inserted rather than rejected. Location and size
    stay null; the header only carries where the job is, which is the posting's
    business and already lives on FactJob.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
        company_name (str | None): The name of the company, or None when the
            extract could not find one.

    Returns:
        int | None: The ID of the company, or None when there is no name.
    """
    if company_name is None:
        return None

    connection.execute(
        """
        INSERT INTO DimCompany (company_name)
        VALUES (?)
        ON CONFLICT(company_name) DO NOTHING
        """,
        (company_name,),
    )

    # Separate SELECT rather than lastrowid: on conflict nothing is inserted
    # and lastrowid would still hold whatever the previous statement wrote.
    row = connection.execute(
        "SELECT id FROM DimCompany WHERE company_name = ?", (company_name,)
    ).fetchone()

    return row[0]


def _solve_role_id(connection: sqlite3.Connection, role_name: str | None) -> int | None:
    """
    Solves the role name to its corresponding ID.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
        role_name (str | None): Canonical role name, or None when the
            identifier recognised no role.

    Returns:
        int | None: The ID of the role, or None when there is no name.

    Raises:
        UnknownSeedValue: The name is not in DimRole.
    """
    if role_name is None:
        return None

    row = connection.execute(
        "SELECT id FROM DimRole WHERE role_name = ?", (role_name,)
    ).fetchone()
    if row is None:
        raise UnknownSeedValue(f"role {role_name!r} is not in DimRole")

    return row[0]


def _solve_degree_id(connection: sqlite3.Connection, degree_name: str | None) -> int | None:
    """
    Solves the degree name to its corresponding ID.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
        degree_name (str | None): Canonical field of study, or None when the
            posting required no degree.

    Returns:
        int | None: The ID of the degree, or None when there is no name.

    Raises:
        UnknownSeedValue: The name is not in DimDegree.
    """
    if degree_name is None:
        return None

    row = connection.execute(
        "SELECT id FROM DimDegree WHERE name = ?", (degree_name,)
    ).fetchone()
    if row is None:
        raise UnknownSeedValue(f"degree {degree_name!r} is not in DimDegree")

    return row[0]


def _solve_technology_name_id(connection: sqlite3.Connection, technology_name: str) -> int:
    """
    Solves the technology name to its corresponding ID.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
        technology_name (str): Canonical technology name.

    Returns:
        int: The ID of the technology.

    Raises:
        UnknownSeedValue: The name is not in DimTechnologies.
    """
    row = connection.execute(
        "SELECT id FROM DimTechnologies WHERE name = ?", (technology_name,)
    ).fetchone()
    if row is None:
        raise UnknownSeedValue(f"technology {technology_name!r} is not in DimTechnologies")

    return row[0]


def _solve_concept_name_id(connection: sqlite3.Connection, concept_name: str) -> int:
    """
    Solves the concept name to its corresponding ID.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
        concept_name (str): Canonical concept name.

    Returns:
        int: The ID of the concept.

    Raises:
        UnknownSeedValue: The name is not in DimConcepts.
    """
    row = connection.execute(
        "SELECT id FROM DimConcepts WHERE concept_name = ?", (concept_name,)
    ).fetchone()
    if row is None:
        raise UnknownSeedValue(f"concept {concept_name!r} is not in DimConcepts")

    return row[0]


def _solve_seniority_id(
    connection: sqlite3.Connection,
    seniority: str | None,
    min_experience: int | None,
) -> int | None:
    """
    Solves the seniority level to its corresponding ID.

    A posting that names a level resolves on the label. One that only states
    years falls back to the label whose range covers them, which is what the
    year columns on DimSeniority are for.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
        seniority (str | None): Canonical label, or None when the posting never
            named a level.
        min_experience (int | None): Years the posting demands for the role as
            a whole. Only read when there is no label.

    Returns:
        int | None: The ID of the seniority level, or None when the posting
            gave neither a label nor years.

    Raises:
        UnknownSeedValue: The label is not in DimSeniority.
    """
    if seniority is not None:
        row = connection.execute(
            "SELECT id FROM DimSeniority WHERE label = ?", (seniority,)
        ).fetchone()
        if row is None:
            raise UnknownSeedValue(f"seniority {seniority!r} is not in DimSeniority")

        return row[0]

    if min_experience is None:
        return None

    # Half-open on the upper bound, so 2 years reads as ssr rather than junior:
    # the seed ends junior at 2 and starts ssr there, and the higher of two
    # adjacent labels is the safer read of a posting that asks for exactly the
    # boundary. The ordering then breaks the overlaps: bounded ranges before
    # open-ended ones and narrower before wider, which sends 0 years to trainee
    # over junior. The typical_min_exp tiebreak is what keeps 7 years at senior
    # instead of lead, and that is the point of the fallback: lead is a
    # statement about responsibility, and a posting that means it says so in
    # words.
    row = connection.execute(
        """
        SELECT id FROM DimSeniority
        WHERE typical_min_exp <= ?
          AND (typical_max_exp IS NULL OR ? < typical_max_exp)
        ORDER BY
            CASE WHEN typical_max_exp IS NULL THEN 1 ELSE 0 END,
            typical_max_exp - typical_min_exp,
            typical_min_exp
        LIMIT 1
        """,
        (min_experience, min_experience),
    ).fetchone()

    return row[0] if row is not None else None


def _solve_post_date(scrape_date: str, posted_days_ago: int | None) -> str | None:
    """
    Solves the posting date by walking back from the day it was scraped.

    Args:
        scrape_date (str): ISO 8601 date the page was saved.
        posted_days_ago (int | None): Days elapsed at scrape time, already
            coarse: LinkedIn only ever reports "hace 3 meses" and the extract
            reads that as 90.

    Returns:
        str | None: ISO 8601 date, or None when the posting stated no age.
    """
    if posted_days_ago is None:
        return None

    return (date.fromisoformat(scrape_date) - timedelta(days=posted_days_ago)).isoformat()


def _load_bridge(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    job_id: int,
    entries: list[tuple[int, dict]],
):
    """
    Insert one job's rows into JobTechnologies or JobConcepts.

    Args:
        connection (sqlite3.Connection): Open connection to the database.
        table (str): Bridge table name.
        column (str): Column holding the dimension id on that table.
        job_id (int): FactJob id the rows hang off.
        entries (list[tuple[int, dict]]): Pairs of required flag and the entry
            the identifier reported, required ones first.
    """
    connection.executemany(
        # DO NOTHING against the (job_id, dimension) primary key. A posting can
        # name the same technology in both lists, and since the required rows
        # are handed over first, must-have wins over nice-to-have.
        f"""
        INSERT INTO {table} (job_id, {column}, required, min_exp, max_exp)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(job_id, {column}) DO NOTHING
        """,
        [
            (
                job_id,
                dimension_id,
                required,
                entry["min_experience"],
                entry["max_experience"],
            )
            for required, dimension_id, entry in entries
        ],
    )


def load(transformed_data: dict, connection: sqlite3.Connection) -> int | None:
    """
    Loads the transformed data into the database.

    One posting, one transaction: either the fact row and both bridges land or
    none of them do. A posting already in the base is skipped rather than
    rewritten, since status is edited by hand once you apply and a re-run must
    not walk that back.

    Args:
        transformed_data (dict): The data to load. Carries scrape_date, stamped
            by extract from the saved page's mtime and passed through transform.

    Returns:
        int | None: The FactJob id, or None when the posting was already there.

    Raises:
        UnknownSeedValue: A canonical name has no row in its dimension.
    """
    header = transformed_data["header"]
    role = transformed_data["role"]
    seniority = transformed_data["seniority"]
    degree = transformed_data["degree"]
    scrape_date = transformed_data["scrape_date"]

    with connection:
        company_id = _solve_company_name_id(connection, header["company_name"])
        role_id = _solve_role_id(connection, role["name"])
        seniority_id = _solve_seniority_id(
            connection, seniority["label"], seniority["min_experience"]
        )

        cursor = connection.execute(
            """
            INSERT INTO FactJob (
                linkedin_job_id, position_name, company_id, role_id, seniority_id,
                post_date, post_date_raw, scrape_date, source_url, location,
                days_at_the_office, raw_text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(linkedin_job_id) DO NOTHING
            """,
            (
                header["linkedin_job_id"],
                header["position_name"],
                company_id,
                role_id,
                seniority_id,
                _solve_post_date(scrape_date, header["posted_days_ago"]),
                header["posted_raw"],
                scrape_date,
                header["source_url"],
                header["location"],
                _MODALITY_DAYS.get(header["modality"]),
                transformed_data["body"],
            ),
        )

        # Nothing inserted means the conflict fired and the posting is already
        # loaded. lastrowid would be stale, so bail before touching the bridges.
        if cursor.rowcount == 0:
            return None

        job_id = cursor.lastrowid

        technologies = transformed_data["technologies"]
        _load_bridge(
            connection,
            "JobTechnologies",
            "technology_id",
            job_id,
            [
                (required, _solve_technology_name_id(connection, entry["name"]), entry)
                for required, entries in (
                    (1, technologies["required_technologies"]),
                    (0, technologies["nice_to_have_technologies"]),
                )
                for entry in entries
            ],
        )

        concepts = transformed_data["concepts"]
        _load_bridge(
            connection,
            "JobConcepts",
            "concept_id",
            job_id,
            [
                (required, _solve_concept_name_id(connection, entry["name"]), entry)
                for required, entries in (
                    (1, concepts["required_concepts"]),
                    (0, concepts["nice_to_have_concepts"]),
                )
                for entry in entries
            ],
        )

        # Its own insert rather than _load_bridge: JobDegrees carries none of the
        # required/min_exp/max_exp columns that helper writes. DO NOTHING covers
        # a posting that names the same field twice.
        connection.executemany(
            """
            INSERT INTO JobDegrees (job_id, degree_id)
            VALUES (?, ?)
            ON CONFLICT(job_id, degree_id) DO NOTHING
            """,
            [
                (job_id, _solve_degree_id(connection, entry["name"]))
                for entry in degree["degrees"]
            ],
        )

    return job_id
