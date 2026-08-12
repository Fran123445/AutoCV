from llm.agents.tech_identifier.first_pass import run_first_pass
from llm.agents.tech_identifier.merge import merge_passes
from llm.agents.tech_identifier.models import TechnologyList
from llm.agents.tech_identifier.second_pass import run_second_pass


def _identify_technologies(job_desc: str) -> TechnologyList:
    """
    Identify technologies in a job description.

    Runs the extraction pass, then a review pass that hunts for what the first
    one missed, and returns the two merged.

    Args:
        job_desc (str): The job description text.

    Returns:
        TechnologyList: The technologies the posting requires, the ones it
            treats as desirable, and the terms neither pass could match.
    """
    first_pass = run_first_pass(job_desc)
    second_pass = run_second_pass(job_desc, first_pass)

    return merge_passes(first_pass, second_pass)


def transform(jd_json: dict) -> dict:
    """
    Transform a job description

    Args:
        jd_json (dict): The job description JSON.

    Returns:
        dict: The transformed job description.
    """

    job_desc = jd_json["body"]

    return {
        "header": jd_json["header"],
        # Carried through rather than dropped: FactJob.raw_text needs it, and
        # the load stage should not have to reopen the extract output to get it.
        "body": job_desc,
        "technologies": _identify_technologies(job_desc).model_dump(),
    }
