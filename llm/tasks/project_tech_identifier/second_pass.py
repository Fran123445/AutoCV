from llm.client import post_chat

from .models import ProjectTechnologyList, SecondPassResult
from .registry import NAMES_WITH_ALIASES
from .render import render_signals


PROMPT_TEMPLATE = """You are reviewing a first pass of technology extraction over a source code repository. The first pass found the technologies in <already_found> and recorded the terms it could not match in <unmatched>. Your job is to catch what it missed.

In the allowed list, parentheses hold alternative spellings of the same technology: "apache spark (spark)" means evidence naming "Spark" is referring to apache spark.

Rules:
- Report only technologies the repository uses and that are absent from <already_found>. Never repeat one that is already there.
- Start with <unmatched>. Most of those are package or module names rather than technology names, and the technology they belong to is in the allowed list under its own spelling: "psycopg2" resolves to postgresql, "torch" to pytorch, "sklearn" to scikit-learn, "boto3" to aws. When one resolves, report the technology and put the original term in resolved_terms.
- Leave a term out of resolved_terms when it is a concept, a methodology or a category rather than a technology: RAG, CI/CD, NoSQL, big data, APIs, relational databases, vector databases. Leave it out too when it is a small utility that belongs to no technology in the list.
- Then re-read the evidence for technologies the first pass overlooked entirely. The places they hide: an imported package whose technology is listed under a different name, an extension with a high count and no matching entry, a framework visible only in the tree layout, a database or queue named in the infrastructure files, a service named in the readme.
- Return empty lists when the first pass missed nothing.

Allowed technologies:
{tech_list}

<already_found>
{already_found}
</already_found>

<unmatched>
{unmatched}
</unmatched>

<repository_evidence>
{evidence}
</repository_evidence>
"""


def run_second_pass(signals: dict, first_pass: ProjectTechnologyList) -> SecondPassResult:
    """
    Review a first pass and report the technologies it missed.

    Args:
        signals (dict): A signal dict as produced by etl.projects.extract.
        first_pass (ProjectTechnologyList): What the first pass reported.
    """
    prompt = PROMPT_TEMPLATE.format(
        tech_list=NAMES_WITH_ALIASES,
        already_found=", ".join(sorted(first_pass.technologies)) or "(nothing)",
        unmatched=", ".join(first_pass.discarded_technologies) or "(nothing)",
        evidence=render_signals(signals),
    )

    return SecondPassResult.model_validate(
        post_chat(
            prompt,
            SecondPassResult.model_json_schema(),
            task_name="project_tech_identifier.second_pass",
        )
    )
