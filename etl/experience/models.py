"""
Shape of experience.toml, as read off disk.

These models describe the file, not the database: the names match the TOML keys
and every field is still a raw string. Canonicalising against the dims, parsing
the dates and rewriting the prose all happen in transform, so what lands here is
only what the file itself can be wrong about — a misspelled key, a missing id,
two projects claiming the same one.
"""

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, StringConstraints, model_validator


def _blank_to_none(value: object) -> object:
    """
    Read an empty string as an absent value.

    TOML has no null, so a field the user did not fill arrives as "" rather than
    missing. Without this the two ways of leaving something out — blanking the
    value or deleting the line — would reach the database as different things.

    Args:
        value (object): Whatever TOML parsed for the field.

    Returns:
        object: None for a string that is empty or only whitespace, the stripped
            string for any other string, and anything else untouched.
    """
    if isinstance(value, str):
        return value.strip() or None

    return value


# Every optional field in the file. Prose goes through it too: stripping costs
# nothing there and drops the trailing newline TOML leaves on a ''' block.
Text = Annotated[str | None, BeforeValidator(_blank_to_none)]

# The dedupe keys. Not Text, because a blank one is not an absent value but a
# broken file: ids are what keep a second run from duplicating rows.
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _reject_duplicate_ids(identifiers: list[str], scope: str):
    """
    Refuse two blocks sharing an id.

    A collision here is silent everywhere else: both projects resolve to the
    same source_path, so the second one overwrites the first at load and the
    file still looks complete.

    Args:
        identifiers (list[str]): The ids found, in file order.
        scope (str): Where they were found, for the error message.

    Raises:
        ValueError: If any id appears more than once.
    """
    duplicates = sorted({key for key in identifiers if identifiers.count(key) > 1})

    if duplicates:
        raise ValueError(f"duplicate ids in {scope}: {', '.join(duplicates)}")


class _Block(BaseModel):
    # extra="forbid" is most of the point of validating at all: `compnay` would
    # otherwise be dropped in silence and surface three stages later as a job
    # with no company, long after the typo is out of sight.
    model_config = ConfigDict(extra="forbid")


class Link(_Block):
    kind: Text = None
    url: Text = None


class Profile(_Block):
    full_name: Text = None
    email: Text = None
    phone: Text = None
    location: Text = None
    birth_date: Text = None
    link: list[Link] = []


class Education(_Block):
    degree: Text = None
    institution: Text = None
    start: Text = None
    end: Text = None


class Project(_Block):
    id: Identifier
    story: Text = None


class Job(_Block):
    id: Identifier
    company: Text = None
    role: Text = None
    seniority: Text = None
    start: Text = None
    end: Text = None
    day_to_day: Text = None
    project: list[Project] = []

    @model_validator(mode="after")
    def _unique_project_ids(self) -> "Job":
        _reject_duplicate_ids([project.id for project in self.project], f"job '{self.id}'")

        return self


class Experience(_Block):
    profile: Profile
    education: list[Education] = []
    job: list[Job] = []
    personal_project: list[Project] = []

    @model_validator(mode="after")
    def _unique_ids(self) -> "Experience":
        _reject_duplicate_ids([job.id for job in self.job], "jobs")
        _reject_duplicate_ids(
            [project.id for project in self.personal_project], "personal projects"
        )

        return self
