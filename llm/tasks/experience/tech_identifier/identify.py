from llm.client import post_chat
from llm.registries.technologies import NAMES_WITH_ALIASES

from .models import ExperienceTechnologyList


# One pass rather than two, and the aliases go in from the start. The review
# pass the jobs and projects sides run exists to recover entries scattered over
# a long document; a day_to_day block is a couple of paragraphs, and there is
# nowhere in it for a technology to hide. What there is no second chance at is
# vocabulary: the block is usually written in Spanish, so a first pass shown
# only canonical names would discard half of what it reads.
PROMPT_TEMPLATE = """You are a technology identifier. Read the account delimited below, written by a candidate about a job they held, and report the technologies they worked with.

In the allowed list, parentheses hold alternative spellings of the same technology: "apache spark (spark)" means an account saying "Spark" is referring to apache spark.

Rules:
- Use only names from the allowed list. Never invent one and never reword one.
- technologies: every technology the account shows the candidate working with. A job has no required or optional split, so report a single flat list.
- The account names technologies in passing rather than in a list. "unos cuarenta DAGs en Airflow, casi todos Python con Spark abajo, escribiendo a Snowflake" is four technologies, not one.
- Report a technology only when the candidate worked with it. What the rest of the team used, what the company runs elsewhere, and what they weighed up and rejected are context, not their own work.
- The account may be in Spanish, in English or in both. The allowed list is English: match through the aliases and report the canonical name.
- discarded_technologies: technologies or tools the account names as the candidate's own work but that have no match in the allowed list.

Allowed technologies:
{tech_list}

<job_account>
{day_to_day}
</job_account>
"""


def identify_technologies(day_to_day: str) -> ExperienceTechnologyList:
    """
    Identify the technologies a candidate worked with in one job.

    Args:
        day_to_day (str): The job's day_to_day block, as written in
            experience.toml.

    Returns:
        ExperienceTechnologyList: The technologies found, and the terms the
            registry could not match.
    """
    prompt = PROMPT_TEMPLATE.format(
        tech_list=NAMES_WITH_ALIASES,
        day_to_day=day_to_day,
    )

    return ExperienceTechnologyList.model_validate(
        post_chat(
            prompt,
            ExperienceTechnologyList.model_json_schema(),
            task_name="experience.tech_identifier.identify",
        )
    )
