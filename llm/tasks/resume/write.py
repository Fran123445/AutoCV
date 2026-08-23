from llm.client import post_chat

from .models import ResumePromptContext, ResumeResponse
from .render import render_candidate


# The two bullet lists are asked for differently on purpose. A position the
# candidate held goes on the CV whether or not the posting cares about it, since
# a gap in the work history reads worse than a weak entry; a personal project
# that has nothing to do with the posting is just noise, and there are far more
# of them than there is room for. So every position gets an entry and personal
# projects are opted into.
PROMPT_TEMPLATE = """You are writing a candidate's CV for one specific job. Read the job description and the candidate's record, both delimited below, and report the summary, the skills block, and the bullets each entry should carry.

What separates a CV that gets read from one that does not is whether each line says how something was made to work. A reader who already builds these systems is looking for the decision behind the work: what was compared against what, what was separated from what, what the shape of the thing was. Naming the task and the library it used tells them nothing they could not have guessed. Write every line for that reader.

Rules for voice, everywhere:
- English. Never write "the candidate", "they", or the candidate's name. Every line reads as the candidate's own, with the subject left off: "Build a reconciliation tool", "Modelled a message archive as a star schema".
- Work still going on takes the present tense, work that has finished takes the past tense. Judge that per position and per project from the dates in the record, not from where the entry sits.

Rules for summary:
- One to three short paragraphs, each its own item in the list. The first is required, the rest are worth adding only when there is something to put in them.
- Open the first on what the candidate is, how long they have been doing it, and in what setting: a role, then the tenure the record gives, then the environment the work happened in. Never open on a bare verb and never on a category.
- A second paragraph, where you write one, sets out the range of the work as concrete kinds of system rather than adjectives.
- Everything in the record is available here, including the education and any work project listed with no position.

Rules for skills:
- Three to six rows, each a label and its items. Choose labels that fit this candidate against this posting rather than working from a fixed set, and put the row the posting cares about most first.
- Draw only on the skills list and on what the record shows the candidate using. Leave out anything the posting has no use for: the list given to you is everything they have ever touched, not everything worth printing.
- Where a term has a common short and long form, print both once, long form first, since the posting may be searched for either: "Extract Transform Load (ETL)", "software development life cycle (SDLC)". Do not do this to terms that only ever appear one way.
- Leave the spoken languages out of the block: they are printed in their own section, straight from the record. A row labelled Languages is programming languages.
- Group tightly enough that the label means something. A row called Other, or a row mixing languages with methodologies, is a row wasted.
- Focus on matching keywords and concepts as they are written out in the job description.

Rules for work_bullets:
- One entry per position in the work history, always, even for a position the posting has no use for. Never more than one entry for the same position.
- source_experience_id: the number on that position's "--- experience N ---" line. Use only ids that appear there.
- Three or four bullets for a position the posting fits, one or two for one it does not. Fewer and longer beats more and shorter: a position with several projects under it should get its strongest three, not one bullet each.
- Draw them from that position's day to day and from the projects listed under it. A project under a position is that position's work: it has no entry of its own and everything it shows belongs here.

Rules for personal_bullets:
- One entry per personal project worth showing for this posting, and no entry at all for the rest. Two is the ceiling and the usual number: the two the posting has most use for, written to the bottom, beat four written to the surface. Write one where only one fits. Never more than one entry for the same project.
- source_project_id: the number on that project's "--- project N ---" line, taken from the personal projects section. Use only ids that appear there.
- title: what the project is, not what its folder is called. The folder name is a private joke or an abbreviation and means nothing to the reader: "Schizo_measurements" is a personal messaging analytics warehouse, "tp-2024-1c-Frituras" is an operating system simulator. Three to six words, in title case, describing the system.
- technologies: the few worth printing beside the title, the ones the posting asks for first. Three to six, not the whole list the record carries.
- Three or four bullets each, and no two of them on the same layer of the system: how the data moves through it, how its pieces are held apart, what constraint it was built against and what that forced. The room the projects you left out would have taken is what pays for this, so use it.
- Make sure to explain the end product of each project so the reader knows what value is derived (if any).

Rules for every bullet:
- Start on the verb, with the subject left off, and vary it: two bullets in a row opening on "Built" or "Developed" read as one bullet.
- One piece of work per bullet, and inside it say how the work was made to do its job. The mechanism is the point: "sampling matched row sets on natural keys and comparing at column level with exact and fuzzy string matching to surface field mappings" is a bullet, "using Pandas and RapidFuzz to perform fuzzy matching" is a library credit. Where the record gives a reason a thing was done one way and not another, that reason is the best material on the page.
- Roughly twenty five to fifty words. One sentence carrying subordinate clauses reads better here than two short ones.
- Integrate the required technology directly with the mechanism or architectural pattern, never as a stand-alone passive mention.
- Carry over every figure, volume, scale, count and result the record states: row counts, sizes, storage reclaimed, how many of a thing were handled, how much of a set was covered. These are the strongest marks on the page and the record is the only place they can come from, so dropping one to be safe costs more than any other mistake here.
- Never state a number, an outcome, a scale or a responsibility the record does not. Do not round a figure the record gives, do not report part of a thing as all of it, and do not turn a task into ownership of a system. Repeating what the record states and inventing what it does not are different acts: this rule forbids the second and never the first.
- Do not spend a bullet on a category name. "Built an ETL pipeline" and "Developed a backend application" say nothing by themselves; say what moved out of where, through what shape, into what.
- Do not repeat the company name, the role or the dates. Those are already printed on the entry.
- Do not repeat the same work across two bullets in different words.
- Reach for the posting's own vocabulary over the record's wherever both describe the same thing.

<job_description>
{job_desc}
</job_description>

<candidate>
{candidate}
</candidate>
"""


def write_resume(context: ResumePromptContext) -> ResumeResponse:
    """
    Write one candidate's summary, skills and bullets against one job description.

    Args:
        context (ResumePromptContext): Candidate and job data for one resume.

    Returns:
        ResumeResponse: The document's written parts, keyed by source id.
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
