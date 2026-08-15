from llm.client import post_chat

from .models import SecondPassResult, TechnologyList
from .registry import NAMES_WITH_ALIASES


PROMPT_TEMPLATE = """You are reviewing a first pass of technology extraction over a job description. The first pass found the technologies in <already_found> and recorded the terms it could not match in <unmatched>. Your job is to catch what it missed.

In the allowed list, parentheses hold alternative spellings of the same technology: "apache spark (spark)" means a posting saying "Spark" is referring to apache spark.

Rules:
- Report only technologies that appear in the job description and are absent from <already_found>. Never repeat one that is already there.
- Start with <unmatched>. Many of those terms are a technology in the allowed list under a different spelling. When one resolves, report the technology and put the original term in resolved_terms.
- Leave a term out of resolved_terms when it is a concept, a methodology or a category rather than a technology: RAG, CI/CD, NoSQL, big data, APIs, relational databases, vector databases.
- Then re-read the job description for technologies the first pass overlooked entirely. Long comma-separated lists are where they hide.
- Sort each one into required or nice-to-have: required for anything under requirements or phrased as mandatory, nice-to-have for "deseable", "nice to have", "a plus", "preferred", "bonus", "valorable", "no excluyente".
- min_experience and max_experience: years demanded for that specific technology, and only when the description states them. Use null when it says nothing.
- Ignore anything that appears only in benefits, perks or company boilerplate.
- Return empty lists when the first pass missed nothing.

Allowed technologies:
{tech_list}

<already_found>
{already_found}
</already_found>

<unmatched>
{unmatched}
</unmatched>

<job_description>
{job_desc}
</job_description>
"""


def run_second_pass(job_desc: str, first_pass: TechnologyList) -> SecondPassResult:
    """
    Review a first pass and report the technologies it missed.

    Args:
        job_desc (str): The job description text.
        first_pass (TechnologyList): What the first pass reported.
    """
    already_found = sorted(
        {tech.name for tech in first_pass.required_technologies}
        | {tech.name for tech in first_pass.nice_to_have_technologies}
    )

    prompt = PROMPT_TEMPLATE.format(
        tech_list=NAMES_WITH_ALIASES,
        already_found=", ".join(already_found) or "(nothing)",
        unmatched=", ".join(first_pass.discarded_technologies) or "(nothing)",
        job_desc=job_desc,
    )

    return SecondPassResult.model_validate(
        post_chat(
            prompt,
            SecondPassResult.model_json_schema(),
            task_name="tech_identifier.second_pass",
        )
    )
