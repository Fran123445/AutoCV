"""
Canonical name to dimension id, for whichever pipeline is asking.

The dimensions are seeded once and shared: a posting asking for 'postgresql' and
a candidate claiming it have to land on the same DimTechnologies row, or the
match compares nothing. These live here rather than on the job side because all
three loaders resolve names, and two of them would otherwise be importing the
third's privates.
"""

import sqlite3


class UnknownSeedValue(Exception):
    """
    A canonical name reached the load stage without a row in its dimension.

    Never a posting's fault. Constrained decoding means the identifiers can
    only ever emit names from the registries, so this fires when the base was
    seeded from an older seeds/ than the one that produced the transform
    output. Re-running db_creation.py is the fix.

    The experience file is the one source that can trip this on its own: it is
    written by hand, so a degree or a role nobody canonicalised reaches load as
    typed.
    """


def solve_company_name_id(connection: sqlite3.Connection, company_name: str | None) -> int | None:
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


def solve_role_id(connection: sqlite3.Connection, role_name: str | None) -> int | None:
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


def solve_degree_id(connection: sqlite3.Connection, degree_name: str | None) -> int | None:
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


def solve_technology_name_id(connection: sqlite3.Connection, technology_name: str) -> int:
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


def solve_concept_name_id(connection: sqlite3.Connection, concept_name: str) -> int:
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


def solve_seniority_id(
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
