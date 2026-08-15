from etl.projects.sample import build_sample
from llm.agents.project_describer.describe import describe
from llm.agents.project_narrator.models import ProjectNarrative
from llm.agents.project_narrator.narrate import narrate
from llm.agents.project_tech_identifier.first_pass import run_first_pass as tech_first_pass
from llm.agents.project_tech_identifier.merge import merge_passes as merge_tech_passes
from llm.agents.project_tech_identifier.models import ProjectTechnologyList
from llm.agents.project_tech_identifier.second_pass import run_second_pass as tech_second_pass


def _identify_technologies(signals: dict) -> ProjectTechnologyList:
    """
    Identify the technologies a project is built with.

    Same two-pass shape as the job side: extract, then review for what the first
    pass missed. The review carries the aliases, which matter more here than on
    a posting, since a manifest names packages rather than technologies.

    Args:
        signals (dict): A signal dict as produced by etl.projects.extract.

    Returns:
        ProjectTechnologyList: The technologies found, and the terms neither
            pass could match.
    """
    first_pass = tech_first_pass(signals)
    second_pass = tech_second_pass(signals, first_pass)

    return merge_tech_passes(first_pass, second_pass)


def _narrate(technologies: list[str], sample: str) -> ProjectNarrative:
    """
    Describe what a project does and which concepts it demonstrates.

    Args:
        technologies (list[str]): Canonical names from the technology pass.
        sample (str): Source sample as built by etl.projects.sample.

    Returns:
        ProjectNarrative: The project's story and its concept tags.
    """
    return narrate(technologies, sample)


def transform(signals: dict) -> dict:
    """
    Transform one project's extracted signals into its identified evidence.

    Three stages, each needing the one before it. The technologies come from
    declarations alone, which is why that stage never opens a source file. The
    sample is then chosen around those technologies, and read twice: once for
    what the project is, once for the part each item plays in it.

    Args:
        signals (dict): A signal dict as produced by etl.projects.extract.

    Returns:
        dict: The identified project.
    """
    technologies = _identify_technologies(signals)
    sample = build_sample(signals["path"], signals, technologies.technologies)

    narrative = _narrate(technologies.technologies, sample)
    descriptions = describe(
        narrative.task_desc,
        technologies.technologies,
        narrative.concepts,
        sample,
    )

    return {
        "path": signals["path"],
        "name": signals["name"],
        "technologies": technologies.model_dump(),
        "narrative": narrative.model_dump(),
        "descriptions": descriptions,
    }
