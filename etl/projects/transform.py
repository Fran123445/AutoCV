from llm.tasks.projects.analyzer.analyze import analyze


def transform(signals: dict) -> dict:
    """
    Transform one project's extracted signals into its identified evidence.

    One call now, not three stages: the whole repo is dumped and read in a
    single pass that returns technologies, concepts, the narrative and the
    per-item descriptions together. The result is reshaped into the same dict
    etl.projects.load expects.

    Args:
        signals (dict): A signal dict as produced by etl.projects.extract.

    Returns:
        dict: The identified project.
    """
    return analyze(signals)
