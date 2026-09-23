import pytest

from etl.candidate import DEFAULT_USER_ID
from etl.experience.load import MissingProjectStory, load


# --------------------------------------------------------------------------
# Builders for the transformed dict load eats
# --------------------------------------------------------------------------
#
# load takes the shape etl.experience.transform leaves, which is deeply nested:
# a job carries a day_to_day and a list of projects, each project an identified
# block of technologies, a narrative and per-item descriptions. Retyping that per
# test would bury the one field a test is about, so the builders default every
# layer and each test overrides only what it exercises — the same bargain
# make_page strikes on the extract side.
#
# The dimension names are real seed entries so the loader's solve_* calls resolve
# rather than raise; an id read back off the base is the wrong thing to assert on,
# so the tests read the name behind it instead.


def make_descriptions(technologies=None, concepts=None):
    """The describer's output: a phrase per named technology or concept."""
    return {
        "technologies": technologies or [],
        "concepts": concepts or [],
    }


def make_identified(
    technologies=("python",),
    concepts=("agile",),
    task_desc="Built the thing.",
    descriptions=None,
):
    """One project's identified block, as three passes leave it."""
    return {
        "technologies": {"technologies": list(technologies)},
        "narrative": {"task_desc": task_desc, "concepts": list(concepts)},
        "descriptions": descriptions or make_descriptions(),
    }


def make_project(id="p1", identified=...):
    """A project block. `identified=None` is the empty-story case load rejects."""
    return {
        "id": id,
        # Sentinel, not None as the default: None is a real value a test sets on
        # purpose to reach MissingProjectStory, so it must not be the fallback.
        "identified": make_identified() if identified is ... else identified,
    }


def make_day_to_day(technologies=("python",), concepts=("agile",), prose="Ran the team."):
    """A job's day_to_day, as its two passes leave it."""
    return {
        "technologies": {"technologies": list(technologies)},
        "narrative": {"day_to_day": prose, "concepts": list(concepts)},
    }


def make_job(
    id="j1",
    company="Acme",
    title="Data Engineer",
    role="backend dev",
    seniority="senior",
    start_date="2019-03",
    end_date=None,
    day_to_day=None,
    projects=None,
):
    return {
        "id": id,
        "company": company,
        "title": title,
        "role": role,
        "seniority": seniority,
        "start_date": start_date,
        "end_date": end_date,
        "day_to_day": day_to_day,
        "projects": projects or [],
    }


def make_experience(profile=None, education=None, languages=None, jobs=None):
    return {
        "profile": profile or make_profile(),
        "education": education or [],
        "languages": languages or [],
        "jobs": jobs or [],
    }


def make_profile(
    full_name="Ada Lovelace",
    email="ada@example.com",
    phone="555",
    location="Buenos Aires",
    birth_date="1990-01-01",
    links=None,
):
    return {
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "location": location,
        "birth_date": birth_date,
        "links": links if links is not None else [],
    }


# --------------------------------------------------------------------------
# profile, written on every run
# --------------------------------------------------------------------------

def test_the_profile_lands_on_fact_user(seeded_db):
    load(make_experience(profile=make_profile(full_name="Ada", email="a@b.co")), seeded_db)

    row = seeded_db.execute(
        "SELECT full_name, email FROM FactUser WHERE id = ?", (DEFAULT_USER_ID,)
    ).fetchone()

    assert row == ("Ada", "a@b.co")


def test_the_profile_is_updated_not_skipped_on_a_second_run(seeded_db):
    """
    One user row, and the file is its only source: a re-run after fixing a phone
    number has to reach the base, unlike everything else the ETL skips on conflict.
    """
    load(make_experience(profile=make_profile(phone="111")), seeded_db)
    load(make_experience(profile=make_profile(phone="222")), seeded_db)

    phone = seeded_db.execute(
        "SELECT phone FROM FactUser WHERE id = ?", (DEFAULT_USER_ID,)
    ).fetchone()[0]

    assert phone == "222"


def test_a_half_filled_link_is_dropped(seeded_db):
    """
    The template ships link kinds with blank urls: a row with one side missing is
    a line the candidate has not written, and both columns are NOT NULL.
    """
    profile = make_profile(links=[
        {"kind": "github", "url": "https://github.com/ada"},
        {"kind": "linkedin", "url": None},
    ])
    load(make_experience(profile=profile), seeded_db)

    kinds = [
        row[0]
        for row in seeded_db.execute(
            "SELECT kind FROM UserLink WHERE user_id = ?", (DEFAULT_USER_ID,)
        )
    ]

    assert kinds == ["github"]


# --------------------------------------------------------------------------
# education and languages
# --------------------------------------------------------------------------

def test_education_resolves_the_degree_to_its_dim(seeded_db):
    education = [{
        "degree": "computer science",
        "institution": "UBA",
        "gpa": "9",
        "start_date": "2010",
        "end_date": "2015",
    }]
    load(make_experience(education=education), seeded_db)

    degree = seeded_db.execute(
        """
        SELECT dd.name
        FROM UserEducation ue
        JOIN DimDegree dd ON dd.id = ue.degree_id
        WHERE ue.user_id = ?
        """,
        (DEFAULT_USER_ID,),
    ).fetchone()[0]

    assert degree == "computer science"


def test_a_language_lands_under_its_name(seeded_db):
    load(make_experience(languages=[{"name": "English", "level": "C1"}]), seeded_db)

    row = seeded_db.execute(
        "SELECT name, level FROM UserLanguage WHERE user_id = ?", (DEFAULT_USER_ID,)
    ).fetchone()

    assert row == ("English", "C1")


# --------------------------------------------------------------------------
# jobs
# --------------------------------------------------------------------------

def test_a_job_lands_with_its_dims_resolved_and_counted(seeded_db):
    job = make_job(role="backend dev", seniority="senior", day_to_day=make_day_to_day(prose="Led it."))
    counts = load(make_experience(jobs=[job]), seeded_db)

    row = seeded_db.execute(
        """
        SELECT dr.role_name, ds.label, fe.job_title, fe.day_to_day, dc.company_name
        FROM FactExperience fe
        JOIN DimRole dr ON dr.id = fe.role_id
        JOIN DimSeniority ds ON ds.id = fe.seniority_id
        JOIN DimCompany dc ON dc.id = fe.company_id
        WHERE fe.user_id = ? AND fe.source_id = ?
        """,
        (DEFAULT_USER_ID, "j1"),
    ).fetchone()

    assert row == ("backend dev", "senior", "Data Engineer", "Led it.", "Acme")
    assert counts["experiences_loaded"] == 1
    assert counts["experiences_skipped"] == 0


def test_a_job_without_a_day_to_day_stores_null_prose(seeded_db):
    load(make_experience(jobs=[make_job(day_to_day=None)]), seeded_db)

    prose = seeded_db.execute(
        "SELECT day_to_day FROM FactExperience WHERE source_id = ?", ("j1",)
    ).fetchone()[0]

    assert prose is None


def test_a_job_seen_before_is_updated_not_duplicated(seeded_db):
    """
    source_id dedupes a re-run: the second load updates the row instead of
    writing a second FactExperience.
    """
    experience = make_experience(jobs=[make_job()])
    load(experience, seeded_db)
    updated = make_experience(jobs=[make_job(title="Staff Data Engineer")])
    counts = load(updated, seeded_db)

    total = seeded_db.execute(
        "SELECT count(*) FROM FactExperience WHERE source_id = ?", ("j1",)
    ).fetchone()[0]

    assert total == 1
    title = seeded_db.execute(
        "SELECT job_title FROM FactExperience WHERE source_id = ?", ("j1",)
    ).fetchone()[0]
    assert title == "Staff Data Engineer"
    assert counts["experiences_loaded"] == 1
    assert counts["experiences_skipped"] == 0


# --------------------------------------------------------------------------
# projects
# --------------------------------------------------------------------------

def test_a_project_lands_with_a_null_source_path(seeded_db):
    """
    A project born from a story carries no repository: source_path stays null,
    which is what tells it apart from one the projects pipeline loaded, and its
    block id goes to source_id to dedupe it.
    """
    job = make_job(projects=[make_project(id="p1", identified=make_identified(task_desc="Shipped it."))])
    counts = load(make_experience(jobs=[job]), seeded_db)

    row = seeded_db.execute(
        "SELECT task_desc, source_path, source_id FROM Project WHERE source_id = ?", ("p1",)
    ).fetchone()

    assert row == ("Shipped it.", None, "p1")
    assert counts["projects_loaded"] == 1


def test_a_projects_tags_land_on_its_bridges_with_their_descriptions(seeded_db):
    identified = make_identified(
        technologies=("python",),
        concepts=("agile",),
        descriptions=make_descriptions(
            technologies=[{"name": "python", "descr": "wrote the pipeline"}],
            concepts=[{"name": "agile", "descr": "ran the ceremonies"}],
        ),
    )
    job = make_job(projects=[make_project(id="p1", identified=identified)])
    load(make_experience(jobs=[job]), seeded_db)

    tech = seeded_db.execute(
        """
        SELECT dt.name, pt.descr
        FROM ProjectTechnologies pt
        JOIN DimTechnologies dt ON dt.id = pt.technology_id
        JOIN Project p ON p.id = pt.project_id
        WHERE p.source_id = ?
        """,
        ("p1",),
    ).fetchone()
    concept = seeded_db.execute(
        """
        SELECT dc.concept_name, pc.descr
        FROM ProjectConcepts pc
        JOIN DimConcepts dc ON dc.id = pc.concept_id
        JOIN Project p ON p.id = pc.project_id
        WHERE p.source_id = ?
        """,
        ("p1",),
    ).fetchone()

    assert tech == ("python", "wrote the pipeline")
    assert concept == ("agile", "ran the ceremonies")


def test_an_empty_project_story_is_refused(seeded_db):
    """
    task_desc is NOT NULL and the transform keeps the empty block rather than
    dropping it, precisely so it is refused here instead of vanishing.
    """
    job = make_job(projects=[make_project(id="p1", identified=None)])

    with pytest.raises(MissingProjectStory):
        load(make_experience(jobs=[job]), seeded_db)


def test_a_project_seen_before_is_updated_not_duplicated(seeded_db):
    job = make_job(projects=[make_project(id="p1")])
    experience = make_experience(jobs=[job])
    load(experience, seeded_db)
    updated_job = make_job(projects=[make_project(
        id="p1",
        identified=make_identified(
            technologies=("javascript",),
            concepts=("scrum",),
            task_desc="Rebuilt the thing.",
            descriptions=make_descriptions(
                technologies=[{"name": "javascript", "descr": "new role"}],
                concepts=[{"name": "scrum", "descr": "new approach"}],
            ),
        ),
    )])
    counts = load(make_experience(jobs=[updated_job]), seeded_db)

    total = seeded_db.execute(
        "SELECT count(*) FROM Project WHERE source_id = ?", ("p1",)
    ).fetchone()[0]

    assert total == 1
    project = seeded_db.execute(
        "SELECT task_desc FROM Project WHERE source_id = ?", ("p1",)
    ).fetchone()[0]
    assert project == "Rebuilt the thing."
    technologies = seeded_db.execute(
        """
        SELECT dt.name, pt.descr
        FROM ProjectTechnologies pt
        JOIN DimTechnologies dt ON dt.id = pt.technology_id
        JOIN Project p ON p.id = pt.project_id
        WHERE p.source_id = ?
        """,
        ("p1",),
    ).fetchall()
    concepts = seeded_db.execute(
        """
        SELECT dc.concept_name, pc.descr
        FROM ProjectConcepts pc
        JOIN DimConcepts dc ON dc.id = pc.concept_id
        JOIN Project p ON p.id = pc.project_id
        WHERE p.source_id = ?
        """,
        ("p1",),
    ).fetchall()
    assert technologies == [("javascript", "new role")]
    assert concepts == [("scrum", "new approach")]
    assert counts["projects_loaded"] == 1
    assert counts["projects_skipped"] == 0


def test_removed_jobs_and_projects_are_removed_from_the_snapshot(seeded_db):
    first = make_experience(jobs=[make_job(projects=[make_project(id="p1")])])
    load(first, seeded_db)

    load(make_experience(), seeded_db)

    assert seeded_db.execute(
        "SELECT count(*) FROM FactExperience WHERE source_id = ?", ("j1",)
    ).fetchone()[0] == 0
    assert seeded_db.execute(
        "SELECT count(*) FROM Project WHERE source_id = ?", ("p1",)
    ).fetchone()[0] == 0
    assert seeded_db.execute(
        "SELECT count(*) FROM UserTechnologies WHERE user_id = ?", (DEFAULT_USER_ID,)
    ).fetchone()[0] == 0


# --------------------------------------------------------------------------
# rollup onto the user bridges
# --------------------------------------------------------------------------

def test_the_rollup_is_the_union_of_job_and_project_tags(seeded_db):
    """
    UserTechnologies answers 'has this candidate touched X', so it collects what
    the day_to_day and every project named, deduped across both.
    """
    job = make_job(
        day_to_day=make_day_to_day(technologies=("python",), concepts=("agile",)),
        projects=[make_project(
            id="p1",
            identified=make_identified(technologies=("javascript",), concepts=("scrum",)),
        )],
    )
    load(make_experience(jobs=[job]), seeded_db)

    technologies = {
        row[0]
        for row in seeded_db.execute(
            """
            SELECT dt.name
            FROM UserTechnologies ut
            JOIN DimTechnologies dt ON dt.id = ut.technology_id
            WHERE ut.user_id = ?
            """,
            (DEFAULT_USER_ID,),
        )
    }
    concepts = {
        row[0]
        for row in seeded_db.execute(
            """
            SELECT dc.concept_name
            FROM UserConcepts uc
            JOIN DimConcepts dc ON dc.id = uc.concept_id
            WHERE uc.user_id = ?
            """,
            (DEFAULT_USER_ID,),
        )
    }

    assert technologies == {"python", "javascript"}
    assert concepts == {"agile", "scrum"}
