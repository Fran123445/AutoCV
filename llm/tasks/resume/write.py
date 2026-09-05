from llm.client import LLMClient

from .models import ResumePromptContext, ResumeResponse
from .render import render_candidate
from resume_generator.localization import resolve_locale


# The two bullet lists are asked for differently on purpose. A position the
# candidate held goes on the CV whether or not the posting cares about it, since
# a gap in the work history reads worse than a weak entry; a personal project
# that has nothing to do with the posting is just noise, and there are far more
# of them than there is room for. So every position gets an entry and personal
# projects are opted into.
PROMPT_TEMPLATE = """Produce an ATS-readable CV tailored to the target job. Return only fields allowed by the response schema.

Your objective is to make the strongest truthful case for an interview in a fast first review. Use the target job as the relevance standard and the candidate record as the only evidence base.

Decision framework:
1. Identify the role's essential responsibilities, required capabilities and domain terms. Give greatest weight to requirements stated as required, primary responsibilities, or repeated throughout the posting.
2. Match each requirement only to direct, specific candidate evidence. Prioritize evidence by: directness of match, demonstrated outcome or scope, recency, and seniority. Do this reasoning silently.
3. Spend the limited page on the highest-value matches first. Preserve the full work history, but use minimal space on entries that cannot strengthen the case.
4. Mirror the posting's exact terminology only when the candidate evidence supports it. Prefer the employer's common term over a synonym so both an applicant system and a human can recognize the match.

Truth and credibility:
- Never invent or infer tools, duties, metrics, ownership, seniority, dates, or proficiency. Do not convert related experience into an unsupported claim.
- Every claim must be traceable to the candidate record.
- Put verifiable achievements before routine duties. When the record supports it, write each bullet as: action + relevant object or method + concrete outcome, scope, or business purpose.
- Preserve exact numbers. Use a metric only when it is meaningful evidence; never manufacture a number or use a vague magnitude.
- Do not keyword-stuff. A skills list is an index of supported evidence, not a list of desirable terms.

Writing rules:
- Write every generated field in {language}. Keep company, product, credential, and technology names in their standard form.
- Write every bullet in first-person past tense, using the localized equivalent of “I” and a strong action verb (for example, “Built…” or “Construí…”). Apply past tense even to a current position: describe completed contributions without inventing an end date.
- Never write the candidate's name, "the candidate", or pronouns such as "they". The summary must also be in first-person, past tense.
- Do not use em dashes, filler, soft-skill labels, or generic assertions such as "hard-working", "passionate", "results-oriented", or "responsible for".
- Do not repeat content across the summary, skills, work history, or projects. Do not repeat company names, roles, or dates already shown by the layout.

Output structure:
- summary: exactly one 35-55 word paragraph. Open with the target professional profile, then state the two or three strongest supported qualifications for this role. It must be a value proposition, not a biography or objective statement.
- skills: 3-5 concise, readable groups with 3-6 items each. Put the role's highest-priority supported terms first. Use conventional group labels. Exclude spoken languages and unsupported tools.
- work_bullets: return exactly one entry for every supplied position, keyed by source_experience_id. Give directly relevant positions 2-3 bullets and other positions 1 concise bullet. Use a position's nested work projects as evidence for that position only.
- personal_bullets: include only personal projects that directly reinforce an important job requirement, at most two. Key each by source_project_id. Give each a clear 3-5 word descriptive title, 3-5 supported technologies, and exactly 2 bullets.

Bullet quality and length:
- Use one distinct achievement, contribution, or responsibility per bullet; avoid stacked claims.
- Write around 12-22 words per bullet.
- Include a method or technology only when it substantiates the match; end with the outcome, scope, or purpose when supported.

Final quality gate:
- Keep only content that improves relevance, credibility, or scanability for this specific role.
- The complete content must fit comfortably on one page in the supplied layout.
- Return no explanation or text outside the response schema.

<job_description>
{job_desc}
</job_description>

<candidate>
{candidate}
</candidate>
"""


def write_resume(
    context: ResumePromptContext, llm_client: LLMClient
) -> ResumeResponse:
    """
    Write one candidate's summary, skills and bullets against one job description.

    Written in the posting's own language: a Spanish posting is read by Spanish
    speakers, and a CV answering it in English asks them to do the translating.

    Args:
        context (ResumePromptContext): Candidate and job data for one resume.

    Returns:
        ResumeResponse: The document's written parts, keyed by source id.
    """
    prompt = PROMPT_TEMPLATE.format(
        language=resolve_locale(context.language).llm_name,
        job_desc=context.job_description,
        candidate=render_candidate(context),
    )

    return ResumeResponse.model_validate(
        llm_client.post_chat(
            prompt,
            ResumeResponse.model_json_schema(),
            task_name="resume.write",
        )
    )
