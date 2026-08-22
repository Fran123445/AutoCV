from llm.tasks.projects.analyzer.analyze import analyze


def transform(signals: dict, author_email: str | None = None) -> dict:
    """
    Transform one project's extracted signals into its identified evidence.

    One call now, not three stages: the whole repo is dumped and read in a
    single pass that returns technologies, concepts, the narrative and the
    per-item descriptions together. The result is reshaped into the same dict
    etl.projects.load expects.

    Args:
        signals (dict): A signal dict as produced by etl.projects.extract.
        author_email (str | None): The CV author's email, so the analyzer can
            point out which contributor in the per-folder split is the author.

    Returns:
        dict: The identified project.
    """
    return analyze(signals, author_email)
