from datetime import date, timedelta

import sqlite3

from etl.dims import (
    solve_company_name_id,
    solve_concept_name_id,
    solve_degree_id,
    solve_role_id,
    solve_seniority_id,
    solve_technology_name_id,
)


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
        company_id = solve_company_name_id(connection, header["company_name"])
        role_id = solve_role_id(connection, role["name"])
        seniority_id = solve_seniority_id(
            connection, seniority["label"], seniority["min_experience"]
        )

        cursor = connection.execute(
            """
            INSERT INTO FactJob (
                linkedin_job_id, position_name, company_id, role_id, seniority_id,
                post_date, post_date_raw, scrape_date, source_url, location,
                days_at_the_office, language, raw_text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                transformed_data["language"],
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
                (required, solve_technology_name_id(connection, entry["name"]), entry)
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
                (required, solve_concept_name_id(connection, entry["name"]), entry)
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
                (job_id, solve_degree_id(connection, entry["name"]))
                for entry in degree["degrees"]
            ],
        )

    return job_id
