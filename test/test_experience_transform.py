import pytest

from etl.experience.models import (
    Education,
    Experience,
    Job,
    Language,
    Link,
    Profile,
    Project,
)
from etl.experience.transform import (
    _parse_date,
    _transform_education,
    _transform_language,
    _transform_profile,
    transform,
)


# --------------------------------------------------------------------------
# Builders for the Experience models transform eats
# --------------------------------------------------------------------------
#
# The mirror image of test_experience_load's builders: those default the shape
# transform leaves, these default the shape it reads. Each test overrides only
# the block it exercises, so the field under test is not buried in template.
#
# Only the prose-free paths are touched here. A non-None day_to_day or project
# story runs the LLM identifiers, which are out of scope; every job built below
# leaves both out, so transform stays pure.


def make_profile(
    full_name="Ada Lovelace",
    email="ada@example.com",
    phone="555",
    location="Buenos Aires",
    birth_date="1990-01-01",
    link=None,
):
    return Profile(
        full_name=full_name,
        email=email,
        phone=phone,
        location=location,
        birth_date=birth_date,
        link=link or [],
    )


def make_job(
    id="1",
    company="Acme",
    title="Data Engineer",
    role="backend dev",
    seniority="senior",
    start="2019-03",
    end=None,
    project=None,
):
    return Job(
        id=id,
        company=company,
        title=title,
        role=role,
        seniority=seniority,
        start=start,
        end=end,
        day_to_day=None,
        project=project or [],
    )


def make_experience(profile=None, education=None, language=None, job=None):
    return Experience(
        profile=profile or make_profile(),
        education=education or [],
        language=language or [],
        job=job or [],
    )


# --------------------------------------------------------------------------
# _parse_date
# --------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("2020", "2020"),
    ("2020-06", "2020-06"),
    ("2020-06-15", "2020-06-15"),
])
def test_a_valid_date_passes_through_unchanged(raw, expected):
    """Columns store ISO 8601 as TEXT, so a good date needs no conversion."""
    assert _parse_date(raw) == expected


@pytest.mark.parametrize("raw", [None, "current"])
def test_an_ongoing_date_becomes_none(raw):
    """The schema marks an ongoing job or degree with a null end, not a word."""
    assert _parse_date(raw) is None


@pytest.mark.parametrize("raw", [
    "20",
    "2020-6",
    "2020/06",
    "2020-06-15-01",
    "June 2020",
    "",
])
def test_a_malformed_date_is_refused(raw):
    with pytest.raises(ValueError):
        _parse_date(raw)


# --------------------------------------------------------------------------
# profile
# --------------------------------------------------------------------------

def test_the_profile_is_renamed_onto_the_fact_user_shape():
    profile = make_profile(full_name="Ada", email="a@b.co", phone="111")
    result = _transform_profile(make_experience(profile=profile))

    assert result["full_name"] == "Ada"
    assert result["email"] == "a@b.co"
    assert result["phone"] == "111"


def test_the_profile_birth_date_is_parsed():
    result = _transform_profile(make_experience(profile=make_profile(birth_date="1990")))

    assert result["birth_date"] == "1990"


def test_a_current_birth_date_becomes_null():
    result = _transform_profile(make_experience(profile=make_profile(birth_date="current")))

    assert result["birth_date"] is None


def test_the_links_pass_through_as_kind_url_pairs():
    profile = make_profile(link=[
        Link(kind="github", url="https://github.com/ada"),
        Link(kind="linkedin", url="https://linkedin.com/in/ada"),
    ])
    result = _transform_profile(make_experience(profile=profile))

    assert result["links"] == [
        {"kind": "github", "url": "https://github.com/ada"},
        {"kind": "linkedin", "url": "https://linkedin.com/in/ada"},
    ]


def test_a_profile_with_no_links_gives_an_empty_list():
    result = _transform_profile(make_experience(profile=make_profile(link=[])))

    assert result["links"] == []


# --------------------------------------------------------------------------
# education
# --------------------------------------------------------------------------

def test_an_education_block_is_renamed_with_its_dates_parsed():
    education = [Education(
        degree="computer science",
        institution="UBA",
        gpa="9",
        start="2010",
        end="2015",
    )]
    result = _transform_education(make_experience(education=education))

    assert result == [{
        "degree": "computer science",
        "institution": "UBA",
        "gpa": "9",
        "start_date": "2010",
        "end_date": "2015",
    }]


def test_an_ongoing_degree_carries_a_null_end():
    education = [Education(degree="computer science", institution="UBA", start="2010", end="current")]
    result = _transform_education(make_experience(education=education))

    assert result[0]["end_date"] is None


def test_no_education_gives_an_empty_list():
    assert _transform_education(make_experience(education=[])) == []


# --------------------------------------------------------------------------
# languages
# --------------------------------------------------------------------------

def test_a_language_is_renamed_under_name_and_level():
    result = _transform_language(make_experience(language=[Language(name="English", level="C1")]))

    assert result == [{"name": "English", "level": "C1"}]


def test_a_nameless_language_is_dropped():
    """
    A block with a level but no name is a line left in the template: name is the
    key UserLanguage stores under, so a blank one cannot land.
    """
    language = [
        Language(name="English", level="C1"),
        Language(name=None, level="C2"),
    ]
    result = _transform_language(make_experience(language=language))

    assert result == [{"name": "English", "level": "C1"}]


# --------------------------------------------------------------------------
# jobs (prose-free: day_to_day and every story left out)
# --------------------------------------------------------------------------

def test_a_job_is_renamed_with_its_dates_parsed_and_prose_null():
    job = make_job(id="j1", company="Acme", title="Data Engineer", start="2019-03", end="2021-08")
    result = transform(make_experience(job=[job]))["jobs"]

    assert result[0]["id"] == "j1"
    assert result[0]["company"] == "Acme"
    assert result[0]["title"] == "Data Engineer"
    assert result[0]["start_date"] == "2019-03"
    assert result[0]["end_date"] == "2021-08"
    # day_to_day left out short-circuits before the identifiers run.
    assert result[0]["day_to_day"] is None


def test_an_ongoing_job_carries_a_null_end():
    result = transform(make_experience(job=[make_job(end="current")]))["jobs"]

    assert result[0]["end_date"] is None


def test_a_project_with_no_story_is_kept_with_null_identified():
    """
    An empty story is not dropped here: Project.task_desc is NOT NULL, so the
    row must reach load for it to be the one that refuses it.
    """
    job = make_job(project=[Project(id="p1", story=None)])
    result = transform(make_experience(job=[job]))["jobs"]

    assert result[0]["projects"] == [{"id": "p1", "identified": None}]


def test_the_job_ids_are_the_files_own():
    """load dedupes on these, so they pass through untouched."""
    job = make_job(id="j-42", project=[Project(id="p-7", story=None)])
    result = transform(make_experience(job=[job]))["jobs"]

    assert result[0]["id"] == "j-42"
    assert result[0]["projects"][0]["id"] == "p-7"


# --------------------------------------------------------------------------
# transform: the four blocks wired together
# --------------------------------------------------------------------------

def test_transform_returns_the_four_blocks():
    result = transform(make_experience())

    assert set(result) == {"profile", "education", "languages", "jobs"}


def test_the_blocks_are_independent_and_each_lands():
    experience = make_experience(
        profile=make_profile(full_name="Ada"),
        education=[Education(degree="computer science", institution="UBA", start="2010", end="2015")],
        language=[Language(name="English", level="C1")],
        job=[make_job(id="j1")],
    )
    result = transform(experience)

    assert result["profile"]["full_name"] == "Ada"
    assert result["education"][0]["degree"] == "computer science"
    assert result["languages"] == [{"name": "English", "level": "C1"}]
    assert result["jobs"][0]["id"] == "j1"
