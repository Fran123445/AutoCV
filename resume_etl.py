"""
Runs the resume pipeline: the rows the other three loaded in, one CV out.

The fourth entry point beside jobs_etl.py, projects_etl.py and experience_etl.py,
and the one that reads the base rather than fills it. There is no batch and no
source folder: the unit is one candidate against one posting, named on the
command line, which is why both ids are required rather than defaulted.

The stages split where the cost is. Writing calls the model and the two after
it do not, so a template or stylesheet edit is re-rendered and reprinted from
the written document instead of paying for the CV a second time to look at it.
"""

from pathlib import Path

import argparse

from config import RESUMES_PDF_DIR, RESUMES_RENDER_DIR, RESUMES_WRITE_DIR
from resume_generator.generator import generate_resume
from resume_generator.models import ResumeDocument
from resume_generator.render import render_html
from run_log import RunLogger, record_job_run


def artifact_stem(user_id: int, job_id: int) -> str:
    """
    Name both artifacts of one candidate against one posting.

    Args:
        user_id (int): Candidate the CV is for.
        job_id (int): Posting the CV is written against.

    Returns:
        str: The stem both stages write under and log their rows under. The
            file names on the other three pipelines come from a source file;
            this pipeline has no file to take one from, so the pair of ids is
            the name.
    """
    return f"u{user_id}_j{job_id}"


def write(user_id: int, job_id: int, write_output_dir: Path):
    """
    Write the resume document and save it.

    Args:
        user_id (int): Candidate the CV is for.
        job_id (int): Posting the CV is written against.
        write_output_dir (Path): Where the written document goes.
    """
    stem = artifact_stem(user_id, job_id)

    with RunLogger("resume_write", postings_total=1) as run_log:
        print(f"Writing a resume for user {user_id} against job {job_id}...")
        try:
            with record_job_run(stem) as job_run:
                document = generate_resume(run_log.connection, user_id, job_id)

                job_run.job_id = job_id

                out_path = write_output_dir / f"{stem}.json"
                out_path.write_text(
                    document.model_dump_json(indent=2), encoding="utf-8"
                )
        except Exception:
            run_log.postings_failed = 1
            raise

        run_log.postings_ok = 1

    print(f"\nWrote the resume for user {user_id} against job {job_id} to {out_path}.")


def render(user_id: int, job_id: int, write_output_dir: Path, render_output_dir: Path):
    """
    Render a written resume document as HTML.

    Args:
        user_id (int): Candidate the CV is for.
        job_id (int): Posting the CV was written against.
        write_output_dir (Path): Where the write stage left its JSON.
        render_output_dir (Path): Where the page goes.
    """
    stem = artifact_stem(user_id, job_id)
    json_path = write_output_dir / f"{stem}.json"

    with RunLogger("resume_render", postings_total=1) as run_log:
        print(f"Rendering {json_path}...")
        try:
            # The same telemetry wrapper the model-calling stage uses, so its
            # call list stays empty. job_id stays null too: nothing here reads
            # FactJob, and a stale document would point the column at a posting
            # this run never saw.
            with record_job_run(stem):
                document = ResumeDocument.model_validate_json(
                    json_path.read_text(encoding="utf-8")
                )

                out_path = render_output_dir / f"{stem}.html"
                out_path.write_text(render_html(document), encoding="utf-8")
        except Exception:
            run_log.postings_failed = 1
            raise

        run_log.postings_ok = 1

    print(f"\nRendered {json_path.name} into {out_path}.")


def pdf(user_id: int, job_id: int, render_output_dir: Path, pdf_output_dir: Path):
    """
    Print a rendered resume page as a PDF.

    Args:
        user_id (int): Candidate the CV is for.
        job_id (int): Posting the CV was written against.
        render_output_dir (Path): Where the render stage left its page.
        pdf_output_dir (Path): Where the PDF goes.
    """
    # Imported here rather than beside the others so that the stages before
    # this one keep running on a machine with no WeasyPrint and no Pango
    # installed. Printing is the only stage that needs either.
    from resume_generator.pdf import render_pdf

    stem = artifact_stem(user_id, job_id)
    html_path = render_output_dir / f"{stem}.html"

    with RunLogger("resume_pdf", postings_total=1) as run_log:
        print(f"Printing {html_path}...")
        try:
            # Wrapped like the render stage and for the same reasons: no model
            # is called, so the call list stays empty, and job_id stays null
            # because nothing here reads FactJob either.
            with record_job_run(stem):
                printed = render_pdf(html_path.read_text(encoding="utf-8"))

                out_path = pdf_output_dir / f"{stem}.pdf"
                out_path.write_bytes(printed.pdf)
        except Exception:
            run_log.postings_failed = 1
            raise

        run_log.postings_ok = 1

    print(
        f"\nPrinted {html_path.name} into {out_path} "
        f"over {printed.page_count} page(s)."
    )


STAGES = ("write", "render", "pdf")


def parse_args():
    parser = argparse.ArgumentParser(description="Run the AutoCV resume stages.")
    parser.add_argument(
        "stages",
        nargs="*",
        choices=STAGES,
        default=None,
        help=(
            "Stages to run. Defaults to all of them. They always run in "
            "pipeline order, whatever order you list them in."
        ),
    )
    parser.add_argument(
        "--user-id",
        type=int,
        required=True,
        help="Candidate whose resume should be built.",
    )
    parser.add_argument(
        "--job-id",
        type=int,
        required=True,
        help="Posting the resume is written against.",
    )

    args = parser.parse_args()
    args.stages = args.stages or list(STAGES)

    return args


def main():
    args = parse_args()
    stages = args.stages

    if "write" in stages:
        RESUMES_WRITE_DIR.mkdir(parents=True, exist_ok=True)
        write(args.user_id, args.job_id, RESUMES_WRITE_DIR)

    if "render" in stages:
        RESUMES_RENDER_DIR.mkdir(parents=True, exist_ok=True)
        render(args.user_id, args.job_id, RESUMES_WRITE_DIR, RESUMES_RENDER_DIR)

    if "pdf" in stages:
        RESUMES_PDF_DIR.mkdir(parents=True, exist_ok=True)
        pdf(args.user_id, args.job_id, RESUMES_RENDER_DIR, RESUMES_PDF_DIR)


if __name__ == "__main__":
    main()
