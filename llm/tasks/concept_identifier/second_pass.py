from llm.client import post_chat

from .models import ConceptList, SecondPassResult
from .registry import NAMES_WITH_ALIASES


PROMPT_TEMPLATE = """You are reviewing a first pass of concept extraction over a job description. The first pass found the concepts in <already_found> and recorded the terms it could not match in <unmatched>. Your job is to catch what it missed.

In the allowed list, parentheses hold alternative spellings of the same concept: "generative ai (genai, ia generativa)" means a posting saying "IA generativa" is referring to generative ai.

Rules:
- Report only concepts that appear in the job description and are absent from <already_found>. Never repeat one that is already there.
- Start with <unmatched>. Many of those terms are a concept in the allowed list under a different spelling, often the Spanish one. When one resolves, report the concept and put the original term in resolved_terms.
- Leave a term out of resolved_terms when it names a product, a tool or a vendor rather than a concept: Docker, Snowflake, Power BI, SAP. Those belong to a different list.
- Then re-read the job description for concepts the first pass overlooked entirely. The responsibilities paragraphs are where they hide: what the role does day to day is stated there rather than in the requirements bullets.
- Sort each one into required or nice-to-have: required for anything under requirements or phrased as mandatory, nice-to-have for "deseable", "nice to have", "a plus", "preferred", "bonus", "valorable", "no excluyente".
- Give the optional block a second read of its own. First passes strip the products out of a section headed "It Is a Plus If You Also Have" or "Requisitos deseables" and walk past the concepts sitting next to them, so that block is where the missing nice-to-have entries usually are.
- min_experience and max_experience: years demanded for that specific concept, and only when the description states them. Use null when it says nothing.
- Ignore anything that appears only in benefits, perks or company boilerplate.
- Return empty lists when the first pass missed nothing.

Allowed concepts:
{concept_list}

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


def run_second_pass(job_desc: str, first_pass: ConceptList) -> SecondPassResult:
    """
    Review a first pass and report the concepts it missed.

    Args:
        job_desc (str): The job description text.
        first_pass (ConceptList): What the first pass reported.
    """
    already_found = sorted(
        {concept.name for concept in first_pass.required_concepts}
        | {concept.name for concept in first_pass.nice_to_have_concepts}
    )

    prompt = PROMPT_TEMPLATE.format(
        concept_list=NAMES_WITH_ALIASES,
        already_found=", ".join(already_found) or "(nothing)",
        unmatched=", ".join(first_pass.discarded_concepts) or "(nothing)",
        job_desc=job_desc,
    )

    return SecondPassResult.model_validate(
        post_chat(
            prompt,
            SecondPassResult.model_json_schema(),
            task_name="concept_identifier.second_pass",
        )
    )
