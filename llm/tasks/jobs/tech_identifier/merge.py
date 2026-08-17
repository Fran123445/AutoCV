from .models import SecondPassResult, TechnologyList


def merge_passes(
    first_pass: TechnologyList, second_pass: SecondPassResult
) -> TechnologyList:
    """
    Fold what the review pass recovered into the first pass result.

    The review reports a delta rather than a standalone result, so its output
    only means anything against the first pass it was computed from. Each rule
    below answers a promise made by the review prompt: change the wording there
    and this has to move with it.

    Args:
        first_pass (TechnologyList): What the first pass reported.
        second_pass (SecondPassResult): What the review recovered.
    """
    # The first pass saw the posting whole, so its placement of a technology
    # wins over the review's when both report the same name.
    seen = {tech.name for tech in first_pass.required_technologies} | {
        tech.name for tech in first_pass.nice_to_have_technologies
    }

    required = list(first_pass.required_technologies)
    nice_to_have = list(first_pass.nice_to_have_technologies)

    for tech in second_pass.missed_required_technologies:
        if tech.name not in seen:
            seen.add(tech.name)
            required.append(tech)

    for tech in second_pass.missed_nice_to_have_technologies:
        if tech.name not in seen:
            seen.add(tech.name)
            nice_to_have.append(tech)

    resolved = {term.casefold() for term in second_pass.resolved_terms}
    discarded = [
        term
        for term in first_pass.discarded_technologies
        if term.casefold() not in resolved
    ]

    return TechnologyList(
        required_technologies=required,
        nice_to_have_technologies=nice_to_have,
        discarded_technologies=discarded,
    )
