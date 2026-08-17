from llm.client import post_chat
from llm.descriptions import build_description_model


# The null cases are stated before the writing rules on purpose, the same as on
# the projects side: the useful answer for a language or a serialization format
# is no answer, and a model given only instructions on how to write will write
# something for every entry.
#
# The null case this pass has and that one does not is attribution. A source
# sample cannot tell you who wrote it, so the projects describer only has to
# decide whether a technology is used at all; here the account names the
# colleague who handled a piece of the work, and a phrase describing that piece
# would put it on the candidate's CV.
PROMPT_TEMPLATE = """You are recording the part each technology and concept played in a project a candidate worked on at a job, so their CV can draw on it later. You are given what the project was, the items to describe, and the account the candidate wrote of it themselves.

Return exactly one entry per item given, keeping the names verbatim.

Leave descr null when:
- The item is the language the work was written in. That it was written in that language is not a fact worth a phrase.
- The item is a serialization or file format used as plumbing, such as json, csv or xml, rather than something the project was built around.
- The account does not say what part the item played. A technology named once in passing and never explained is a null, not a guess.
- The account puts the item on somebody else's side of the work. A phrase describing what a colleague built would read on the CV as the candidate's own.

Otherwise write descr as:
- One short phrase, under fifteen words, naming the part this item played in this project. "merge target for the incremental upsert", "orchestration for the nightly backfill", "schema validation ahead of the load".
- Written in English, whatever language the account is written in. The account is usually Spanish and the phrase never is.
- Grounded in the account, and in the candidate's own share of the work.
- Free of any number the account does not state, and of any outcome it does not claim.
- A phrase, not a sentence. No leading capital, no trailing period, and do not repeat the item's own name inside it.

What the project was:
{task_desc}

Technologies to describe:
{technologies}

Concepts to describe:
{concepts}

<project_account>
{story}
</project_account>
"""


def describe(
    task_desc: str, technologies: list[str], concepts: list[str], story: str
) -> dict:
    """
    Describe the part each technology and concept played in a job's project.

    Args:
        task_desc (str): What the project was, from the narrative pass.
        technologies (list[str]): Canonical names from the technology pass.
        concepts (list[str]): Canonical names from the narrative pass.
        story (str): The project's story block, as written in experience.toml.

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
        story=story,
    )

    return model.model_validate(
        post_chat(
            prompt,
            model.model_json_schema(),
            task_name="experience.project_describer.describe",
        )
    ).model_dump()
