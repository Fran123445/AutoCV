from llm.client import post_chat

from .models import build_description_model


# The null case is stated before the writing rules on purpose: the useful answer
# for a language or a serialization format is no answer, and a model given only
# instructions on how to write will write something for every entry.
PROMPT_TEMPLATE = """You are recording how a personal software project used each of its technologies and concepts, so its author's CV can draw on it later. You are given what the project does, the items to describe, and a sample of its source code.

Return exactly one entry per item given, keeping the names verbatim.

Leave descr null when:
- The item is the language the project is written in. That it is written in that language is not a fact worth a phrase.
- The item is a serialization or file format used as plumbing, such as json, csv or xml, rather than something the project is built around.
- The source sample does not show the item in use. A dependency you can see declared but never see used is a null, not a guess.

Otherwise write descr as:
- One short phrase, under fifteen words, naming the part this item plays in this project. "async job queue for the price scraper", "embeddings store behind the recommendation lookup", "schema migrations for the run log".
- Grounded in the sample. Read purpose from how the code is named, arranged and used, and say that purpose plainly even when no comment states it.
- Free of any number you were not shown: no user counts, no percentages, no speedups, no volumes, no durations.
- Free of any claim about outcome or quality. Say what it does in the project, never how well it worked or what it achieved.
- A phrase, not a sentence. No leading capital, no trailing period, and do not repeat the item's own name inside it.

What the project does:
{task_desc}

Technologies to describe:
{technologies}

Concepts to describe:
{concepts}

<source_sample>
{sample}
</source_sample>
"""


def describe(
    task_desc: str, technologies: list[str], concepts: list[str], sample: str
) -> dict:
    """
    Describe the part each technology and concept plays in a project.

    Args:
        task_desc (str): What the project does, from the narrative pass.
        technologies (list[str]): Canonical names from the technology pass.
        concepts (list[str]): Canonical names from the narrative pass.
        sample (str): Source sample as built by etl.projects.sample.

    Returns:
        dict: Description lists keyed by kind, empty when there is nothing to
            describe.
    """
    if not technologies and not concepts:
        return {}

    model = build_description_model(technologies, concepts)
    prompt = PROMPT_TEMPLATE.format(
        task_desc=task_desc,
        technologies=", ".join(technologies) or "(none)",
        concepts=", ".join(concepts) or "(none)",
        sample=sample,
    )

    return model.model_validate(
        post_chat(
            prompt,
            model.model_json_schema(),
            task_name="project_describer.describe",
        )
    ).model_dump()
