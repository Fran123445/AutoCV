from llm.client import post_chat
from llm.registries.concepts import NAMES_WITH_ALIASES
from llm.registries.technologies import drop_technologies

from .models import DayToDayNarrative


# The rule on numbers is the opposite of the projects narrator's, and the
# difference is the source rather than a change of mind. That pass reads source
# code, where a figure the model produces was invented by definition: nothing in
# a repository states how many people used it. This one reads the candidate's
# own account, where "un equipo de seis" and "dos o tres veces por mes" are
# testimony from the only person who can know. Stripping those would throw away
# the part of the block a CV actually needs, so the rule is to carry what is
# stated and never to move it.
PROMPT_TEMPLATE = """You are rewriting a candidate's own account of a job they held, so their CV can draw on it later. You are given the technologies already identified in it. Report what the job consisted of day to day and which concepts it demonstrates.

Rules for day_to_day:
- Three to five sentences. Say what the candidate was responsible for, what they worked on regularly, and what the recurring problems were. Third person, no marketing language, and do not open by naming the company.
- Write in English, whatever language the account is written in.
- The account is testimony, not evidence read off a system: the candidate is the only authority on their own job. Scale, team size, frequencies and outcomes they state are facts, and they should survive into the rewrite rather than be smoothed away.
- Never state a number, an outcome or a responsibility the account does not. Do not round a figure up, do not turn "dos o tres veces por mes" into "constantly", and do not promote something they mention doing once into something they owned.
- Leave out career narrative. How they came to the job, why they left it and what they moved on to next are not what the job consisted of.
- Leave out the company itself. What it sells, how large it is and what it was like to work there are not this candidate's work.

Rules for concepts:
- Use only names from the allowed list. Never invent one and never reword one.
- In the allowed list, parentheses hold alternative spellings of the same concept: "retrieval augmented generation (rag)" means the two name one concept.
- Report a concept only when the account shows the candidate practising it. Something the rest of the team did, or something they say they wish they had done, is not theirs.
- Do not report technologies as concepts. A concept is a practice, a method or a body of knowledge: data pipelines, code review, data quality. The technologies are already known and are listed below only as context.
- discarded_concepts: concepts the account clearly demonstrates that have no match in the allowed list.

Identified technologies:
{technologies}

Allowed concepts:
{concept_list}

<job_account>
{day_to_day}
</job_account>
"""


def narrate(technologies: list[str], day_to_day: str) -> DayToDayNarrative:
    """
    Rewrite one job's day_to_day block and tag the concepts it demonstrates.

    Args:
        technologies (list[str]): Canonical names from the technology pass.
        day_to_day (str): The job's day_to_day block, as written in
            experience.toml.

    Returns:
        DayToDayNarrative: The rewritten prose and its concept tags.
    """
    prompt = PROMPT_TEMPLATE.format(
        technologies=", ".join(technologies) or "(none identified)",
        concept_list=NAMES_WITH_ALIASES,
        day_to_day=day_to_day,
    )

    narrative = DayToDayNarrative.model_validate(
        post_chat(
            prompt,
            DayToDayNarrative.model_json_schema(),
            task_name="experience.narrator.narrate",
        )
    )

    # The grammar keeps the concept list clean, but discarded_concepts is free
    # text and collects technology names however plainly the prompt says not to.
    narrative.discarded_concepts = drop_technologies(narrative.discarded_concepts)

    return narrative
