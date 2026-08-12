from llm.agents.concept_identifier.first_pass import run_first_pass as concepts_first_pass
from llm.agents.concept_identifier.merge import merge_passes as merge_concept_passes
from llm.agents.concept_identifier.models import ConceptList
from llm.agents.concept_identifier.second_pass import run_second_pass as concepts_second_pass
from llm.agents.role_identifier.classify import classify_role
from llm.agents.seniority_identifier.classify import classify_seniority
from llm.agents.tech_identifier.first_pass import run_first_pass as tech_first_pass
from llm.agents.tech_identifier.merge import merge_passes as merge_tech_passes
from llm.agents.tech_identifier.models import TechnologyList
from llm.agents.tech_identifier.second_pass import run_second_pass as tech_second_pass


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
    first_pass = tech_first_pass(job_desc)
    second_pass = tech_second_pass(job_desc, first_pass)

    return merge_tech_passes(first_pass, second_pass)


def _identify_concepts(job_desc: str) -> ConceptList:
    """
    Identify concepts in a job description.

    Same two-pass shape as the technologies: extract, then review for what the
    first pass missed.

    Args:
        job_desc (str): The job description text.

    Returns:
        ConceptList: The concepts the posting requires, the ones it treats as
            desirable, and the terms neither pass could match.
    """
    first_pass = concepts_first_pass(job_desc)
    second_pass = concepts_second_pass(job_desc, first_pass)

    return merge_concept_passes(first_pass, second_pass)


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
        "concepts": _identify_concepts(job_desc).model_dump(),
        "seniority": classify_seniority(job_desc).model_dump(),
        # The only identifier that reads the header: the title settles the role
        # far more often than the description does.
        "role": classify_role(jd_json["header"]["position_name"], job_desc).model_dump(),
    }
