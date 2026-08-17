from llm.client import post_chat
from llm.registries.technologies import NAMES_WITH_ALIASES

from .models import ExperienceTechnologyList


# One identifier for both blocks the experience file carries. A day_to_day and
# a project story are the same kind of evidence — the candidate writing about
# their own work — and the rules for reading one are the rules for reading the
# other, down to the hard part, which is telling their work apart from their
# team's. Two prompts would be the same prompt twice, and a rule fixed in one
# would quietly stop matching the other. What differs is only which block was
# read, and that goes on the call record rather than into the text.
#
# One pass rather than two, and the aliases go in from the start. The review
# pass the jobs and projects sides run exists to recover entries scattered over
# a long document; these blocks are a few paragraphs, and there is nowhere in
# them for a technology to hide. What there is no second chance at is
# vocabulary: they are usually written in Spanish, so a first pass shown only
# canonical names would discard half of what it reads.
PROMPT_TEMPLATE = """You are a technology identifier. Read the account delimited below, written by a candidate about work they did, and report the technologies they worked with.

In the allowed list, parentheses hold alternative spellings of the same technology: "apache spark (spark)" means an account saying "Spark" is referring to apache spark.

Rules:
- Use only names from the allowed list. Never invent one and never reword one.
- technologies: every technology the account shows the candidate working with. This is not a job posting, so there is no required or optional split: report a single flat list.
- The account names technologies in passing rather than in a list. "unos cuarenta DAGs en Airflow, casi todos Python con Spark abajo, escribiendo a Snowflake" is four technologies, not one.
- Report a technology only when the candidate worked with it themselves. An account of a project usually says who did what, and the other side of that line does not count: "otro companero se encargo de adaptar los dashboards de Tableau" is somebody else's work, so Tableau is not reported.
- What the rest of the team used, what the company runs elsewhere, and what the candidate weighed up and decided against are context in the same way. A technology named only as the option not taken was not worked with.
- The account may be in Spanish, in English or in both. The allowed list is English: match through the aliases and report the canonical name.
- discarded_technologies: technologies or tools the account names as the candidate's own work but that have no match in the allowed list.

Allowed technologies:
{tech_list}

<work_account>
{account}
</work_account>
"""


def identify_technologies(account: str, subject: str) -> ExperienceTechnologyList:
    """
    Identify the technologies a candidate worked with, from their own account.

    Args:
        account (str): A day_to_day or a project story block, as written in
            experience.toml.
        subject (str): Which block this is, "day_to_day" or "project". Only
            reaches the call record, so the two can be told apart in
            FactLLMCall without splitting the prompt.

    Returns:
        ExperienceTechnologyList: The technologies found, and the terms the
            registry could not match.
    """
    prompt = PROMPT_TEMPLATE.format(
        tech_list=NAMES_WITH_ALIASES,
        account=account,
    )

    return ExperienceTechnologyList.model_validate(
        post_chat(
            prompt,
            ExperienceTechnologyList.model_json_schema(),
            task_name=f"experience.tech_identifier.{subject}",
        )
    )
