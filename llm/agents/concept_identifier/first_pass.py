from llm.client import post_chat

from .models import ConceptList
from .registry import NAMES_ONLY


# Instructions come first and the description is fenced, so the model can tell
# the two apart: job postings are themselves full of imperative sentences.
PROMPT_TEMPLATE = """You are a concept identifier. Read the job description delimited below and report the concepts it mentions.

A concept is knowledge, a practice or a methodology: what the role expects you to understand. A product you install, buy or write code in is a technology, not a concept, and belongs to a different list. Report "containerization" rather than Docker, "data warehousing" rather than Snowflake, "agile" rather than Jira. When the posting names only the product, report the concept behind it only if the posting talks about the practice itself.

Rules:
- Use only names from the allowed list. Never invent one and never reword one.
- required_concepts: what the posting demands. Anything listed under requirements, or phrased as required, mandatory, "must have", "solid knowledge of", "conocimiento solido", "experiencia en".
- nice_to_have_concepts: what the posting treats as optional or advantageous: "deseable", "nice to have", "a plus", "preferred", "bonus", "valorable", "no excluyente".
- min_experience and max_experience: years demanded for that specific concept, and only when the description states them. Use null when it says nothing. A general figure such as "2+ years of experience" belongs to the role rather than to any one concept, so do not copy it onto every entry.
- discarded_concepts: concepts, practices or methodologies named in the description that have no match in the allowed list. Leave product and tool names out of it, they are handled elsewhere.
- The responsibilities section counts. A posting that says "disenar y mantener pipelines de datos" is asking for data pipelines even if no requirements bullet repeats it.
- Ignore anything that appears only in benefits, perks or company boilerplate. Report what the role actually uses or requires.

Allowed concepts:
{concept_list}

<job_description>
{job_desc}
</job_description>
"""


def run_first_pass(job_desc: str) -> ConceptList:
    """
    Identify concepts mentioned in a job description.

    Args:
        job_desc (str): The job description text.
    """
    prompt = PROMPT_TEMPLATE.format(
        concept_list=NAMES_ONLY,
        job_desc=job_desc,
    )

    return ConceptList.model_validate(
        post_chat(prompt, ConceptList.model_json_schema())
    )
