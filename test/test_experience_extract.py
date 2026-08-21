import tomllib

import pytest
from pydantic import ValidationError

from etl.experience.extract import extract


def write_toml(tmp_path, text):
    """
    Drop TOML on disk and hand back its path.

    extract takes a Path and opens it, so the tests need a real file rather than
    a parsed dict; testing model_validate on a dict would exercise the model and
    skip the one thing extract itself does, which is read the file off disk.
    """
    path = tmp_path / "experience.toml"
    path.write_text(text, encoding="utf-8")

    return path


# A profile block is the one thing every file must carry: Experience.profile has
# no default, so its own table has to be present even when every field is blank.
MINIMAL = "[profile]\n"


# --------------------------------------------------------------------------
# extract, over a well-formed file
# --------------------------------------------------------------------------

def test_extract_reads_the_profile(tmp_path):
    path = write_toml(tmp_path, '[profile]\nfull_name = "Ada Lovelace"\nemail = "ada@example.com"\n')

    experience = extract(path)

    assert experience.profile.full_name == "Ada Lovelace"
    assert experience.profile.email == "ada@example.com"


def test_extract_reads_a_job_and_its_nested_project(tmp_path):
    """The array-of-tables nesting is the shape the transform stage walks."""
    path = write_toml(tmp_path, (
        '[profile]\n'
        'full_name = "Ada"\n'
        '[[job]]\n'
        'id = "j1"\n'
        'company = "Acme"\n'
        '[[job.project]]\n'
        'id = "p1"\n'
        'story = "shipped the thing"\n'
    ))

    experience = extract(path)

    assert experience.job[0].id == "j1"
    assert experience.job[0].company == "Acme"
    assert experience.job[0].project[0].id == "p1"


def test_extract_reads_a_blank_field_as_absent(tmp_path):
    """
    TOML has no null: a field the candidate left empty arrives as "" and the
    model's BeforeValidator turns it into None, so a deleted line and a blanked
    one reach the pipeline as the same thing. The surrounding value is stripped.
    """
    path = write_toml(tmp_path, '[profile]\nfull_name = "  Ada  "\nemail = ""\n')

    experience = extract(path)

    assert experience.profile.full_name == "Ada"
    assert experience.profile.email is None


# --------------------------------------------------------------------------
# extract, over a broken file
# --------------------------------------------------------------------------

def test_extract_raises_on_invalid_toml(tmp_path):
    """A syntax error is tomllib's to reject, before the model ever sees a dict."""
    path = write_toml(tmp_path, "this is = = not valid toml")

    with pytest.raises(tomllib.TOMLDecodeError):
        extract(path)


def test_extract_raises_when_the_profile_is_missing(tmp_path):
    """profile has no default, so a file without the block is incomplete."""
    path = write_toml(tmp_path, '[[job]]\nid = "j1"\n')

    with pytest.raises(ValidationError):
        extract(path)


def test_extract_raises_on_a_misspelled_key(tmp_path):
    """
    extra="forbid" is the reason to validate at all: "compnay" would otherwise be
    dropped in silence and surface stages later as a job with no company.
    """
    path = write_toml(tmp_path, '[profile]\n[[job]]\nid = "j1"\ncompnay = "Acme"\n')

    with pytest.raises(ValidationError):
        extract(path)


def test_extract_raises_on_duplicate_job_ids(tmp_path):
    """The ids dedupe a re-run; two blocks sharing one would overwrite silently."""
    path = write_toml(tmp_path, MINIMAL + '[[job]]\nid = "same"\n[[job]]\nid = "same"\n')

    with pytest.raises(ValidationError):
        extract(path)


def test_extract_raises_on_duplicate_project_ids_within_a_job(tmp_path):
    path = write_toml(tmp_path, (
        MINIMAL
        + '[[job]]\n'
        'id = "j1"\n'
        '[[job.project]]\n'
        'id = "dup"\n'
        '[[job.project]]\n'
        'id = "dup"\n'
    ))

    with pytest.raises(ValidationError):
        extract(path)


def test_extract_raises_on_a_blank_id(tmp_path):
    """An id is not Text: blank is a broken file, not an absent value."""
    path = write_toml(tmp_path, MINIMAL + '[[job]]\nid = "   "\n')

    with pytest.raises(ValidationError):
        extract(path)
