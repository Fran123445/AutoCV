from pathlib import Path

import tomllib

from etl.experience.models import Experience


def extract(experience_path: Path) -> Experience:
    """
    Read the hand-written experience file into a validated object.

    The thinnest of the three extracts, and deliberately so: the jobs side has
    to pull a posting out of saved HTML, but here the file is already the
    structured artifact. Nothing is written to disk either — an extract folder
    would only hold a copy of the source, since there is no expensive step
    upstream worth caching. The costly stage on this pipeline is transform, and
    that one does stage its output.

    It still exists as its own stage rather than living at the top of transform:
    a transform taking a path owns file IO, which puts the model calls behind a
    fixture on disk and rules out the input/expected-output pairs the job side
    evaluates with.

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
