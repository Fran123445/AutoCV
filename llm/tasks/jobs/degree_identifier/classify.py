from llm.client import LLMClient
from llm.registries.degrees import NAMES_WITH_ALIASES

from .models import DegreeRequirement


# One pass rather than two. The list is short and named in one place in the
# posting, so there is nothing for a review pass to recover: unlike the tech and
# concept passes, a degree is not scattered across the description.
PROMPT_TEMPLATE = """You are a degree identifier. Read the job description delimited below and report every field of study the posting accepts for the candidate.

In the allowed list, parentheses hold alternative spellings of the same field: "information systems engineering (ingenieria en sistemas, licenciatura en sistemas)" means a posting asking for "Ingeniería en Sistemas" requires information systems engineering.

Rules:
- Use only names from the allowed list. Never invent one and never reword one.
- Postings usually list several careers as alternatives: "Ingeniería en Sistemas, Ciencias de la Computación o afines". Report all of them, one entry per field, since holding any one satisfies the posting.
- Report the field of study, never the level: "título de grado en Ingeniería en Sistemas" and "estudiante avanzado de Ingeniería en Sistemas" are both information systems engineering.
- When the posting asks for a broad category such as "carrera de Ingeniería" or "carreras afines a Ingeniería" without naming a specialty, report engineering.
- degrees: empty when the posting requires no degree at all, which is common: many postings ask only for experience. Do not invent a requirement from the technologies or the seniority.
- Ignore degrees that belong to somebody else, such as the background of the team you would join.
- Ignore study requirements that are not a field, such as "secondary school complete" or "English B2".
- unmatched: a required field of study no allowed-list entry fits, copied in the posting's own words. A field that matched the list never appears here.
- evidence: for each matched field, the phrase you read it from, copied verbatim from the description.

Allowed degrees:
{degree_list}

<job_description>
{job_desc}
</job_description>
"""


def classify_degree(
    job_desc: str, llm_client: LLMClient
) -> DegreeRequirement:
    """
    Identify the fields of study a job description accepts.

    Args:
        job_desc (str): The job description text.
    """
    prompt = PROMPT_TEMPLATE.format(
        degree_list=NAMES_WITH_ALIASES,
        job_desc=job_desc,
    )

    return DegreeRequirement.model_validate(
        llm_client.post_chat(
            prompt,
            DegreeRequirement.model_json_schema(),
            task_name="jobs.degree_identifier.classify",
        )
    )
