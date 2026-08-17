from pathlib import Path

import tomllib

from etl.experience.models import Experience


def extract(experience_path: Path) -> Experience:
    """
    Read the hand-written experience file into a validated object.

    The thinnest of the three extracts: the file is already the structured
    artifact, so nothing is written to disk — an extract folder would only
    hold a copy of the source, since there is no expensive step upstream
    worth caching.

    Args:
        experience_path (Path): The filled template, normally config
            .EXPERIENCE_PATH.

    Returns:
        Experience: The file as an object, with blanks read as absent values.

    Raises:
        tomllib.TOMLDecodeError: If the file is not valid TOML.
        pydantic.ValidationError: If a key is misspelled, an id is missing or
            two blocks share one.
    """
    with experience_path.open("rb") as experience_file:
        document = tomllib.load(experience_file)

    return Experience.model_validate(document)
