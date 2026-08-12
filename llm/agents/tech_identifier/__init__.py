from .first_pass import Technology, TechnologyList, run_first_pass
from .second_pass import SecondPassResult, run_second_pass

__all__ = [
    "Technology",
    "TechnologyList",
    "SecondPassResult",
    "run_first_pass",
    "run_second_pass",
    "identify_technologies",
]


def _merge(
    first_pass: TechnologyList, second_pass: SecondPassResult
) -> TechnologyList:
    """
    Fold what the second pass recovered into the first pass result.

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


def identify_technologies(job_desc: str) -> TechnologyList:
    """
    Identify technologies mentioned in a job description.

    Runs the extraction pass, then a review pass that hunts for what the first
    one missed, and returns the two merged.

    Args:
        job_desc (str): The job description text.
    """
    first_pass = run_first_pass(job_desc)
    second_pass = run_second_pass(job_desc, first_pass)

    return _merge(first_pass, second_pass)
