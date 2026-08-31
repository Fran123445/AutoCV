import re

from llm.client import LLMClient
from llm.tasks.jobs.concept_identifier.first_pass import run_first_pass as concepts_first_pass
from llm.tasks.jobs.concept_identifier.merge import merge_passes as merge_concept_passes
from llm.tasks.jobs.concept_identifier.models import ConceptList
from llm.tasks.jobs.concept_identifier.second_pass import run_second_pass as concepts_second_pass
from llm.tasks.jobs.degree_identifier.classify import classify_degree
from llm.tasks.jobs.role_identifier.classify import classify_role
from llm.tasks.jobs.seniority_identifier.classify import classify_seniority
from llm.tasks.jobs.tech_identifier.first_pass import run_first_pass as tech_first_pass
from llm.tasks.jobs.tech_identifier.merge import merge_passes as merge_tech_passes
from llm.tasks.jobs.tech_identifier.models import TechnologyList
from llm.tasks.jobs.tech_identifier.second_pass import run_second_pass as tech_second_pass


# Stopwords are cheaper than an LLM
_SPANISH_MARKERS = frozenset(
    "de la el los las que y en un una para con del por se su sus al como "
    "más lo es son está también desde entre sobre nuestro nuestra".split()
)

_ENGLISH_MARKERS = frozenset(
    "the of and to in for is are with on as you your we our will be that "
    "this at from or an have has their they".split()
)

# Accents kept, digits and punctuation dropped: "más" has to stay one token,
# and nothing outside a word can be a stopword anyway.
_WORD = re.compile(r"[a-záéíóúüñ]+")


def _identify_language(job_desc: str) -> str | None:
    """
    Identify the language a job description is written in.

    Counted rather than asked of a model: es-vs-en over several hundred words
    of prose is settled by function words alone, and a count is deterministic,
    free, and testable offline in a way an extra call is not.

    Args:
        job_desc (str): The job description text.

    Returns:
        str | None: 'es', 'en', or None when the text carries too few function
            words to tell, which in practice means it is not prose.
    """
    words = _WORD.findall(job_desc.casefold())

    spanish = sum(word in _SPANISH_MARKERS for word in words)
    english = sum(word in _ENGLISH_MARKERS for word in words)

    if max(spanish, english) < 5 or abs(spanish - english) < 3:
        return None

    return "es" if spanish > english else "en"


def _identify_technologies(
    job_desc: str, llm_client: LLMClient
) -> TechnologyList:
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
    first_pass = tech_first_pass(job_desc, llm_client)
    second_pass = tech_second_pass(job_desc, first_pass, llm_client)

    return merge_tech_passes(first_pass, second_pass)


def _identify_concepts(
    job_desc: str, llm_client: LLMClient
) -> ConceptList:
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
    first_pass = concepts_first_pass(job_desc, llm_client)
    second_pass = concepts_second_pass(job_desc, first_pass, llm_client)

    return merge_concept_passes(first_pass, second_pass)


def transform(jd_json: dict, llm_client: LLMClient) -> dict:
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
        "scrape_date": jd_json["scrape_date"],
        # Carried through rather than dropped: FactJob.raw_text needs it, and
        # the load stage should not have to reopen the extract output to get it.
        "body": job_desc,
        "language": _identify_language(job_desc),
        "technologies": _identify_technologies(job_desc, llm_client).model_dump(),
        "concepts": _identify_concepts(job_desc, llm_client).model_dump(),
        "seniority": classify_seniority(job_desc, llm_client).model_dump(),
        # The only identifier that reads the header: the title settles the role
        # far more often than the description does.
        "role": classify_role(
            jd_json["header"]["position_name"], job_desc, llm_client
        ).model_dump(),
        "degree": classify_degree(job_desc, llm_client).model_dump(),
    }
