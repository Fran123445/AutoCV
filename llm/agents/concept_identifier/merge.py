from .models import ConceptList, SecondPassResult


def merge_passes(
    first_pass: ConceptList, second_pass: SecondPassResult
) -> ConceptList:
    """
    Fold what the review pass recovered into the first pass result.

    The review reports a delta rather than a standalone result, so its output
    only means anything against the first pass it was computed from. Each rule
    below answers a promise made by the review prompt: change the wording there
    and this has to move with it.

    Args:
        first_pass (ConceptList): What the first pass reported.
        second_pass (SecondPassResult): What the review recovered.
    """
    # The first pass saw the posting whole, so its placement of a concept wins
    # over the review's when both report the same name.
    seen = {concept.name for concept in first_pass.required_concepts} | {
        concept.name for concept in first_pass.nice_to_have_concepts
    }

    required = list(first_pass.required_concepts)
    nice_to_have = list(first_pass.nice_to_have_concepts)

    for concept in second_pass.missed_required_concepts:
        if concept.name not in seen:
            seen.add(concept.name)
            required.append(concept)

    for concept in second_pass.missed_nice_to_have_concepts:
        if concept.name not in seen:
            seen.add(concept.name)
            nice_to_have.append(concept)

    resolved = {term.casefold() for term in second_pass.resolved_terms}
    discarded = [
        term
        for term in first_pass.discarded_concepts
        if term.casefold() not in resolved
    ]

    return ConceptList(
        required_concepts=required,
        nice_to_have_concepts=nice_to_have,
        discarded_concepts=discarded,
    )
