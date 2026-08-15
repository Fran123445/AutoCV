from llm.client import post_chat

from .models import ProjectTechnologyList
from .registry import NAMES_ONLY
from .render import render_signals


# The evidence is labelled and fenced for the same reason the job side fences a
# posting: a readme is full of imperative sentences, and a tree is full of names
# that look like instructions.
PROMPT_TEMPLATE = """You are a technology identifier. Read the evidence gathered from a source code repository, delimited below, and report the technologies the project is built with.

Rules:
- Use only names from the allowed list. Never invent one and never reword one.
- technologies: every technology the project actually uses. A repository has no required or optional split, so report a single flat list.
- Weigh every section. The imported packages are the strongest evidence, since they are what the code actually uses; the manifests come next, since a project can declare a dependency it never imports. Many projects have no manifest at all: the imports, the extension counts, the infrastructure files and the tree layout still say what it is built with.
- Packages are written as import or module names, not as the technology they belong to. Report the technology the package binds to: "psycopg2" is evidence of postgresql, "torch" of pytorch, "sklearn" of scikit-learn, "boto3" of aws.
- File extensions are evidence of their language: .py of python, .rs of rust, .tsx of typescript and react, .sql of sql.
- Report a technology only when the project uses it. A readme comparing the project to something else, or a roadmap of what it might use later, is not use.
- Ignore the packaging of the evidence itself: git is not a technology this project uses just because the files are tracked.
- discarded_technologies: dependencies or tools that are clearly present in the evidence but have no match in the allowed list.

Allowed technologies:
{tech_list}

<repository_evidence>
{evidence}
</repository_evidence>
"""


def run_first_pass(signals: dict) -> ProjectTechnologyList:
    """
    Identify the technologies a project is built with.

    Args:
        signals (dict): A signal dict as produced by etl.projects.extract.
    """
    prompt = PROMPT_TEMPLATE.format(
        tech_list=NAMES_ONLY,
        evidence=render_signals(signals),
    )

    return ProjectTechnologyList.model_validate(
        post_chat(
            prompt,
            ProjectTechnologyList.model_json_schema(),
            agent_name="project_tech_identifier.first_pass",
        )
    )
