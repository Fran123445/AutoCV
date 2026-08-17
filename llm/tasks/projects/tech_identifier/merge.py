from .models import ProjectTechnologyList, SecondPassResult


def merge_passes(
    first_pass: ProjectTechnologyList, second_pass: SecondPassResult
) -> ProjectTechnologyList:
    """
    Fold what the review pass recovered into the first pass result.

    The review reports a delta rather than a standalone result, so its output
    only means anything against the first pass it was computed from. Each rule
    below answers a promise made by the review prompt: change the wording there
    and this has to move with it.

    Simpler than the job side's merge, since a flat list has no required versus
    nice-to-have placement to arbitrate: a name is either already there or new.

    Args:
        first_pass (ProjectTechnologyList): What the first pass reported.
        second_pass (SecondPassResult): What the review recovered.
    """
    technologies = list(first_pass.technologies)
    seen = set(technologies)

    for name in second_pass.missed_technologies:
        if name not in seen:
            seen.add(name)
            technologies.append(name)

    resolved = {term.casefold() for term in second_pass.resolved_terms}
    discarded = [
        term
        for term in first_pass.discarded_technologies
        if term.casefold() not in resolved
    ]

    return ProjectTechnologyList(
        technologies=technologies,
        discarded_technologies=discarded,
    )
