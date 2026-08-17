from llm.client import post_chat
from llm.registries.roles import NAMES_WITH_ALIASES

from .models import Role


# One pass rather than two, for the same reason as the seniority identifier.
#
# The title arrives separately because it is the strongest signal by far, and
# burying it in the description leaves the model to find it again.
PROMPT_TEMPLATE = """You are a role identifier. Read the job title and description delimited below and report which role the posting advertises.

In the allowed list, parentheses hold alternative spellings of the same role: "data engineer (ingeniero de datos, big data engineer)" means a posting titled "Ingeniero de Datos" is advertising data engineer.

Rules:
- Use only names from the allowed list. Never invent one and never reword one.
- The title decides when it is specific. Read the description to settle it when the title is generic, abbreviated, or says only the company and the level.
- Report the most specific role the posting supports. Use software dev only when the posting names no specialty at all: a description that is entirely about pipelines and warehouses is a data engineer even when the title says "Software Engineer".
- A programming language does not settle the role. "Java Developer" or "Python Developer" is whatever the description turns out to describe, and software dev when it describes nothing narrower.
- Seniority words are not part of the role. "Junior Java Developer", "Ssr. Data Scientist" and "Trainee Full Stack Developer" are the same roles as their titles without those words.
- Ignore roles that belong to somebody else. "Reportaras a un data architect" or "trabajaras junto a data scientists" describes the team, not this posting.
- name: null when no entry in the list fits, and put the posting's own wording in unmatched. Fill one or the other, never both.
- Report null for every field when the posting does not advertise a single role at all, such as a job fair, a talent pool or an open application.
- evidence: the phrase you read the role from, copied verbatim from the title or the description.

Allowed roles:
{role_list}

<job_title>
{position_name}
</job_title>

<job_description>
{job_desc}
</job_description>
"""


def classify_role(position_name: str | None, job_desc: str) -> Role:
    """
    Identify the role a job description advertises.

    Args:
        position_name (str | None): The posting title, as extracted from the
            page. Null when the page carried no usable title.
        job_desc (str): The job description text.
    """
    prompt = PROMPT_TEMPLATE.format(
        role_list=NAMES_WITH_ALIASES,
        position_name=position_name or "(the page carried no title)",
        job_desc=job_desc,
    )

    return Role.model_validate(
        post_chat(
            prompt,
            Role.model_json_schema(),
            think=False,
            task_name="jobs.role_identifier.classify",
        )
    )
