from pathlib import Path

from llm.client import post_chat
from llm.registries.concepts import NAMES_ONLY as CONCEPTS_LIST
from llm.registries.technologies import NAMES_ONLY as TECH_LIST

from .models import RepoAnalysis
from .render import (
    SKIP_DIRS,
    _render_contributions,
    _render_files,
    _render_tree,
)


PROMPT_TEMPLATE = """You are analysing a personal software project for its author's CV. You are given the project's file tree and the full text of its tracked files. Report what it does, the technologies it uses and the concepts it demonstrates.

task_desc:
- Two or three sentences. What the project does, the problem it solves, how it is built. Third person, no marketing, do not open by naming the project.
- Read purpose from the code and the README: names, arrangement and what the modules operate on are evidence of intent.
- Never state a number you were not shown, and never claim an outcome, an adoption or a quality. Describe what is there, not what is planned.

technologies:
- Use only names from the allowed technologies list. Never invent one and never reword one.
- Report a technology only when the project actually uses it. Packages are import or module names, not the technology they belong to: "psycopg2" is postgresql, "torch" is pytorch, "sklearn" is scikit-learn, "boto3" is aws. File extensions are evidence of their language.
- For each, descr is two or three sentences on the part it plays in this project and how it is used, grounded in what the code actually does with it, or null for the language the project is written in and for plumbing formats (json, csv, xml). Do not repeat the technology's own name in its descr.

concepts:
- Use only names from the allowed concepts list. Never invent one and never reword one.
- A concept is a practice or method, not a technology: web scraping, etl, unit testing, machine learning. Report one only when the code demonstrates it.
- descr is two or three sentences on how the project demonstrates it, grounded in what the code actually does, or null when it is not really shown.

discarded_technologies / discarded_concepts: things clearly present in the code with no match in the allowed lists.

Allowed technologies:
{tech_list}

Allowed concepts:
{concept_list}

<project_name>
{name}
</project_name>

<file_tree>
{tree}
</file_tree>

<repository_files>
{files}
</repository_files>

<folder_contributions>
Per-folder share of authored commits, by contributor email. Evidence of who built which parts of the project.
{author}{contributions}
</folder_contributions>
"""


def analyze(signals: dict, author_email: str | None = None) -> dict:
    """Run the one-shot analysis for one project's extract signals."""
    # Only worth pointing out when there is a split to read it against: a repo
    # with no contribution data leaves the author line dangling over nothing.
    author = (
        f"The CV's author is {author_email}. Weight their role in the project by "
        "their share of the folders that form its core, and do not credit them "
        "for parts they barely touched.\n"
        if author_email and signals.get("folder_contributions")
        else ""
    )

    prompt = PROMPT_TEMPLATE.format(
        tech_list=TECH_LIST,
        concept_list=CONCEPTS_LIST,
        name=signals["name"],
        tree=_render_tree(
            [p for p in signals["tree"] if p.split("/")[0] not in SKIP_DIRS]
        ),
        files=_render_files(Path(signals["path"]), signals["tree"]),
        author=author,
        contributions=_render_contributions(signals.get("folder_contributions", {})),
    )

    result = RepoAnalysis.model_validate(
        post_chat(
            prompt,
            RepoAnalysis.model_json_schema(),
            task_name="projects.analyzer.analyze",
            think=True,
            reasoning_effort="low",
        )
    )

    # Reshape the one-call response into the dict etl.projects.load expects.
    return {
        "path": signals["path"],
        "name": signals["name"],
       "head_commit": signals.get("head_commit"),
        "first_commit_at": signals.get("first_commit_at"),
        "last_commit_at": signals.get("last_commit_at"),
        "technologies": {
            "technologies": [entry.name for entry in result.technologies],
            "discarded_technologies": result.discarded_technologies,
        },
        "narrative": {
            "task_desc": result.task_desc,
            "concepts": [entry.name for entry in result.concepts],
            "discarded_concepts": result.discarded_concepts,
        },
        "descriptions": {
            "technologies": [entry.model_dump() for entry in result.technologies],
            "concepts": [entry.model_dump() for entry in result.concepts],
        },
    }


