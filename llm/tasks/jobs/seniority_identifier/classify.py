from llm.client import post_chat
from llm.registries.seniority import LABELS_WITH_ALIASES

from .models import Seniority


# One pass rather than two. The review pass the other identifiers run exists to
# recover entries missed in a long list; there is a single answer here, and a
# second look at it would re-litigate a judgement rather than extend a list.
PROMPT_TEMPLATE = """You are a seniority identifier. Read the job description delimited below and report the seniority level of the role it advertises.

In the allowed list, parentheses hold alternative spellings of the same level: "ssr (semi senior, mid)" means a posting saying "Semi Senior" is advertising ssr.

Rules:
- Use only labels from the allowed list. Never invent one and never reword one.
- label: the level the posting names for the role being advertised. The title is the usual place, but a phrase like "buscamos un perfil senior" counts too.
- Report null for label when the posting never names a level. Do not deduce one from years of experience: a posting asking for 5 years without ever saying "senior" has no level, and reporting the years is enough.
- Ignore levels that belong to somebody else. "Reportaras a un tech lead" or "trabajaras con desarrolladores senior" describes the team, not this role.
- When the posting names a range such as "Semi Senior / Senior", report the lower of the two.
- min_experience and max_experience: years demanded for the role as a whole, such as "3+ years of experience" or "entre 2 y 4 años". Use null when the description states none. Years attached to one specific technology are not the role's figure, so ignore those here.
- evidence: the phrase you read the level from, copied verbatim from the description. Null whenever label is null.
- Ignore anything that appears only in benefits, perks or company boilerplate.

Allowed levels:
{label_list}

<job_description>
{job_desc}
</job_description>
"""


def classify_seniority(job_desc: str) -> Seniority:
    """
    Identify the seniority level a job description advertises.

    Args:
        job_desc (str): The job description text.
    """
    prompt = PROMPT_TEMPLATE.format(
        label_list=LABELS_WITH_ALIASES,
        job_desc=job_desc,
    )

    return Seniority.model_validate(
        post_chat(
            prompt,
            Seniority.model_json_schema(),
            think=False,
            task_name="jobs.seniority_identifier.classify",
        )
    )
