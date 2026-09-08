"""Exceptions shared by the job extraction pipeline and source adapters."""


class JobDescriptionNotFound(Exception):
    """Raised when a saved page carries no usable job description."""


class UnsupportedJobSource(ValueError):
    """Raised when no source-specific extractor is registered for a page."""
