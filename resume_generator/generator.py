"""Build renderer-independent resume documents from candidate data."""

import sqlite3

from .models import ResumeDocument, ResumeEducation, ResumeLink, ResumeProfile


def _build_profile(
    connection: sqlite3.Connection,
    user_id: int,
) -> ResumeProfile:
    """Build the resume header from the candidate profile and links."""

    profile = connection.execute(
        """
        SELECT full_name, email, phone, location
        FROM FactUser
        WHERE id = ?
        """,
        (user_id,),
    ).fetchone()

    if profile is None:
        raise ValueError(f"candidate not found: {user_id}")

    full_name, email, phone, location = profile
    
    if full_name is None:
        raise ValueError(f"candidate {user_id} has no full name")

    links = connection.execute(
        """
        SELECT kind, url
        FROM UserLink
        WHERE user_id = ?
        ORDER BY kind
        """,
        (user_id,),
    ).fetchall()

    return ResumeProfile(
        full_name=full_name,
        email=email,
        phone=phone,
        location=location,
        links=[ResumeLink(kind=kind, url=url) for kind, url in links],
    )


def _build_education(
    connection: sqlite3.Connection,
    user_id: int,
) -> list[ResumeEducation]:
    """Build education entries from the candidate's stored education."""

    education = connection.execute(
        """
        SELECT d.name, ue.institution, ue.start_date, ue.end_date
        FROM UserEducation AS ue
        JOIN DimDegree AS d ON d.id = ue.degree_id
        WHERE ue.user_id = ?
        ORDER BY
            ue.end_date IS NULL DESC,
            ue.end_date DESC,
            ue.start_date DESC,
            d.name,
            ue.institution
        """,
        (user_id,),
    ).fetchall()

    return [
        ResumeEducation(
            degree=degree,
            institution=institution,
            start_date=start_date,
            end_date=end_date,
        )
        for degree, institution, start_date, end_date in education
    ]


def generate_resume(
    connection: sqlite3.Connection,
    user_id: int,
) -> ResumeDocument:
    """Build the deterministic portions of one candidate's resume.

    The generator reads candidate data but does not render or export it.  The
    remaining document sections are intentionally left at their model defaults
    until their selection rules are defined.

    Args:
        connection: Open connection to the candidate database.
        user_id: Candidate whose resume should be built.

    Returns:
        A renderer-independent resume document.

    Raises:
        ValueError: If the candidate does not exist or has no name.
    """
    return ResumeDocument(
        profile=_build_profile(connection, user_id),
        education=_build_education(connection, user_id),
    )
