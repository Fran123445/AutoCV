from llm.client import post_chat

from .models import ProjectNarrative
from .registry import NAMES_WITH_ALIASES, drop_technologies


# Aliases rather than bare names, unlike the technology first pass: there is no
# review pass behind this one to bridge a term later, so the only chance to
# recognise "rag" as retrieval augmented generation is here.
PROMPT_TEMPLATE = """You are describing a personal software project for its author's CV. You are given the technologies already identified in it, and a sample of its source code. Report what the project does and which concepts it demonstrates.

Rules for task_desc:
- Two or three sentences. Say what the project does, what problem it solves, and how it is built. Third person, no marketing language, and do not open by naming the project.
- Read purpose from the code. What the modules are called, how they are arranged and what they operate on are evidence of intent, and you should state that intent plainly even when no comment spells it out.
- Never state a number you were not shown. No user counts, no percentages, no speedups, no volumes, no durations, no team sizes. A count is allowed only when the sample lets you count it, such as the number of sources a scraper visibly handles.
- Never claim an outcome. What the project achieved, how well it worked and who used it are not in the code, and inventing them is worse than leaving them out.
- Describe what is there, not what is planned. A roadmap, a TODO or an empty stub is not something the project does.

Rules for concepts:
- Use only names from the allowed list. Never invent one and never reword one.
- In the allowed list, parentheses hold alternative spellings of the same concept: "retrieval augmented generation (rag)" means the two name one concept.
- Report a concept only when the code demonstrates it. A project importing a database driver demonstrates working with that database; a project with one commented-out query does not.
- Do not report technologies as concepts. A concept is a practice, a method or a body of knowledge: web scraping, etl, unit testing, machine learning. The technologies are already known and are listed below only as context.
- discarded_concepts: concepts the project clearly demonstrates that have no match in the allowed list.

Identified technologies:
{technologies}

Allowed concepts:
{concept_list}

<source_sample>
{sample}
</source_sample>
"""


def narrate(technologies: list[str], sample: str) -> ProjectNarrative:
    """
    Describe what a project does and which concepts it demonstrates.

    Args:
        technologies (list[str]): Canonical names from the technology pass.
        sample (str): Source sample as built by etl.projects.sample.

    Returns:
        ProjectNarrative: The project's story and its concept tags.
    """
    prompt = PROMPT_TEMPLATE.format(
        technologies=", ".join(technologies) or "(none identified)",
        concept_list=NAMES_WITH_ALIASES,
        sample=sample,
    )

    narrative = ProjectNarrative.model_validate(
        post_chat(
            prompt,
            ProjectNarrative.model_json_schema(),
            task_name="project_narrator.narrate",
        )
    )

    # The grammar keeps the concept list clean, but discarded_concepts is free
    # text and collects technology names however plainly the prompt says not to.
    narrative.discarded_concepts = drop_technologies(narrative.discarded_concepts)

    return narrative
