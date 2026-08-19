from llm.client import post_chat

from .models import ResumePromptContext, ResumeResponse
from .render import render_candidate


# The two bullet lists are asked for differently on purpose. A position the
# candidate held goes on the CV whether or not the posting cares about it, since
# a gap in the work history reads worse than a weak entry; a personal project
# that has nothing to do with the posting is just noise, and there are far more
# of them than there is room for. So every position gets an entry and personal
# projects are opted into.
PROMPT_TEMPLATE = """You are writing a candidate's CV for one specific job. Read the job description and the candidate's record, both delimited below, and report a summary and the bullets each entry should carry.

Rules for summary:
- Three or four sentences saying what the candidate is and why this posting fits them. Third person, English, and do not name the candidate.
- Say what they have done, not what they are like. "Built the reporting pipeline three teams run on" is a summary; "passionate, detail-oriented team player" is not.
- Lead with what the posting asks for and the candidate has. Everything in the record is available to it, including the education and any work project listed with no position.

Rules for work_bullets:
- One entry per position in the work history, always, even for a position the posting has no use for. Never more than one entry for the same position.
- source_experience_id: the number on that position's "--- experience N ---" line. Use only ids that appear there.
- Three to five bullets for a position the posting fits, one or two for one it does not.
- Draw them from that position's day to day and from the projects listed under it. A project under a position is that position's work: it has no entry of its own and everything it shows belongs here.

Rules for personal_bullets:
- One entry per personal project worth showing for this posting, and no entry at all for the rest. They might not be worth showing. Never more than one entry for the same project.
- source_project_id: the number on that project's "--- project N ---" line, taken from the personal projects section. Use only ids that appear there.
- Two or three bullets each.

Rules for every bullet:
- Third person, English, starting with what the candidate did. Past tense, except for work that is still ongoing.
- Name the technologies and the concepts the record attaches to the work. Where the record says what one was used for, that is the more useful half: "modelled the semantic layer in DAX" beats "used DAX".
- Never state a number, an outcome, a scale or a responsibility the record does not. Do not round a figure, do not turn a task into ownership of a system, and do not fill a thin entry by inventing.
- Do not repeat the company name, the role or the dates. Those are already on the entry.
- Do not repeat the same work across two bullets in different words.
- Match the job descriptions keywords rather than the ones used in the candidate profile.

<job_description>
{job_desc}
</job_description>

<candidate>
{candidate}
</candidate>
"""


def write_resume(context: ResumePromptContext) -> ResumeResponse:
    """
    Write one candidate's summary and bullets against one job description.

    Args:
        context (ResumePromptContext): Candidate and job data for one resume.

    Returns:
        ResumeResponse: The summary and the bullets, keyed by source id.
    """
    prompt = PROMPT_TEMPLATE.format(
        job_desc=context.job_description,
        candidate=render_candidate(context),
    )

    return ResumeResponse.model_validate(
        post_chat(
            prompt,
            ResumeResponse.model_json_schema(),
            task_name="resume.write",
        )
    )
