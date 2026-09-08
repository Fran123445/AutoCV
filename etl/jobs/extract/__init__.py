"""Job-posting extraction entry points.

The source-specific parsers live beside this module.  The public imports stay
compatible with the original ``etl.jobs.extract`` module while the dispatcher
is still LinkedIn-only; Indeed will be added as a separate parser next.
"""

from .linkedin import (
    JobDescriptionNotFound,
    _clean_html,
    _extract_body,
    _extract_company,
    _extract_location,
    _extract_posted,
    _extract_source,
    _longest_common_suffix,
    _read_mhtml,
    extract_from_file,
    extract_from_html,
)

__all__ = [
    "JobDescriptionNotFound",
    "extract_from_file",
    "extract_from_html",
]
