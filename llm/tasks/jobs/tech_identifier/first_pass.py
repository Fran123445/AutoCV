from llm.client import post_chat
from llm.registries.technologies import NAMES_ONLY

from .models import TechnologyList


# Instructions come first and the description is fenced, so the model can tell
# the two apart: job postings are themselves full of imperative sentences.
PROMPT_TEMPLATE = """You are a technology identifier. Read the job description delimited below and report the technologies it mentions.

Rules:
- Use only names from the allowed list. Never invent one and never reword one.
- required_technologies: what the posting demands. Anything listed under requirements, or phrased as required, mandatory, "must have", "solid knowledge of", "conocimiento solido", "experiencia en".
- nice_to_have_technologies: what the posting treats as optional or advantageous: "deseable", "nice to have", "a plus", "preferred", "bonus", "valorable", "no excluyente".
- min_experience and max_experience: years demanded for that specific technology, and only when the description states them. Use null when it says nothing. A general figure such as "2+ years of experience" belongs to the role rather than to any one technology, so do not copy it onto every entry.
- discarded_technologies: technologies or tools named in the description that have no match in the allowed list.
- Ignore anything that appears only in benefits, perks or company boilerplate. Report what the role actually uses or requires.

Allowed technologies:
{tech_list}

<job_description>
{job_desc}
</job_description>
"""


def run_first_pass(job_desc: str) -> TechnologyList:
    """
    Identify technologies mentioned in a job description.

    Args:
        job_desc (str): The job description text.
    """
    prompt = PROMPT_TEMPLATE.format(
        tech_list=NAMES_ONLY,
        job_desc=job_desc,
    )

    return TechnologyList.model_validate(
        post_chat(
            prompt,
            TechnologyList.model_json_schema(),
            task_name="jobs.tech_identifier.first_pass",
        )
    )
