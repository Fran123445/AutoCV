from llm.client import post_chat
from llm.registries.concepts import NAMES_WITH_ALIASES, resolve_concepts
from llm.registries.technologies import drop_technologies

from .models import JobProjectNarrative


# The numbers rule mirrors the day_to_day narrator's and inverts the projects
# narrator's, since this pass reads testimony rather than source code. It also
# carries a rule neither of those has: attribution. A project story is where a
# candidate writes down what they did and what a colleague did, in the same
# paragraph, and a description that quietly folds the second into the first is
# the one way this pass can turn an honest account into a false CV.
PROMPT_TEMPLATE = """You are describing a project a candidate worked on at a job, from the account they wrote of it themselves, so their CV can draw on it later. You are given the technologies already identified in it. Report what the project was and which concepts it demonstrates.

Rules for task_desc:
- Say what problem the project solved, what was built and how, and what came of it. Third person, no marketing language, and do not open by naming the project.
- Eight to twelve sentences for an account with that much in it, fewer only when the account itself is thin. This description is the whole of what anything downstream will ever see of the account, so a detail dropped here is dropped from every CV written from it afterwards. Length is not the cost. Losing the mechanism is.
- Keep the mechanism at the level the account gives it: what was compared against what, what the data was keyed or joined on, how much was sampled, what tolerance or threshold was applied, what shape the output took, what ran against what. These specifics are the reason this pass exists, and a description that keeps only the shape of the task has thrown away the part worth reading.
- Write in English, whatever language the account is written in.
- Describe the candidate's own share of the work. An account of a project usually says who did what: "otro companero se encargo de adaptar los dashboards" is somebody else's work, and it does not belong in this description however central it was to the project. Say what the project was, then what they did in it.
- The account is testimony, not evidence read off a system: the candidate is the only authority on their own work. Scale, durations, frequencies and outcomes they state are facts, and they should survive into the description rather than be smoothed away.
- Never state a number, an outcome or a decision the account does not. Do not round a figure up, do not turn "dos o tres veces por mes" into "constantly", and never credit the candidate with a choice they describe somebody else making.
- Keep the reasoning where the account gives it. Why one approach was chosen over another is the part of a project worth reading, and it is exactly what a list of technologies loses.
- Report an outcome as the account reports it, including the part the candidate does not claim. "no tengo el numero del impacto" is a limit they set on their own claim, and inventing past it is worse than leaving the outcome out.

Rules for concepts:
- Use only names from the allowed list. Never invent one and never reword one.
- In the allowed list, parentheses hold alternative spellings of the same concept: "retrieval augmented generation (rag)" means the two name one concept.
- Report a concept only when the account shows the candidate practising it on this project. A concept the account attributes to a colleague, or names as an approach considered and dropped, is not theirs.
- Do not report technologies as concepts. A concept is a practice, a method or a body of knowledge: change data capture, data modelling, backfilling. The technologies are already known and are listed below only as context.
- discarded_concepts: concepts the project clearly demonstrates that have no match in the allowed list.

Identified technologies:
{technologies}

Allowed concepts:
{concept_list}

<project_account>
{story}
</project_account>
"""


def narrate(technologies: list[str], story: str) -> JobProjectNarrative:
    """
    Describe a project a candidate did at a job, and tag what it demonstrates.

    Args:
        technologies (list[str]): Canonical names from the technology pass.
        story (str): The project's story block, as written in experience.toml.

    Returns:
        JobProjectNarrative: The project's description and its concept tags.
    """
    prompt = PROMPT_TEMPLATE.format(
        technologies=", ".join(technologies) or "(none identified)",
        concept_list=NAMES_WITH_ALIASES,
        story=story,
    )

    narrative = JobProjectNarrative.model_validate(
        post_chat(
            prompt,
            JobProjectNarrative.model_json_schema(),
            task_name="experience.project_narrator.narrate",
        )
    )

    # The grammar keeps the concept list clean, but discarded_concepts is free
    # text and collects technology names however plainly the prompt says not to.
    narrative.discarded_concepts = drop_technologies(narrative.discarded_concepts)

    # And it collects concepts the registry does hold. One pass has no review
    # behind it to catch that, so the recovery happens against the seed.
    recovered, narrative.discarded_concepts = resolve_concepts(
        narrative.discarded_concepts
    )
    narrative.concepts.extend(
        name for name in recovered if name not in narrative.concepts
    )

    return narrative
