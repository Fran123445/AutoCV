"""
Runs the resume pipeline: the rows the other three loaded in, one CV out.

The fourth entry point beside jobs_etl.py, projects_etl.py and experience_etl.py,
and the one that reads the base rather than fills it. There is no batch and no
source folder: the unit is one candidate against one posting, named on the
command line, which is why both ids are required rather than defaulted.

The stages split where the cost is. Writing calls the model and the two after
it do not, so a template or stylesheet edit is re-rendered and reprinted from
the written document instead of paying for the CV a second time to look at it.

All three write into one folder per posting, named for it, so that a CV and the
page and the PDF made from it sit together rather than three stage folders apart.
The artifacts themselves are named from the candidate and the position:
``nombre-apellido-posicion-cv``.
"""

from pathlib import Path

import argparse
import re
import sqlite3
import unicodedata

from app_log import get_logger
from config import RESUMES_DIR
from llm.client import LLMClient
from llm.settings import LLMSettings
from resume_generator.generator import generate_resume
from resume_generator.models import ResumeDocument
from resume_generator.render import render_html
from run_log import RunLogger, record_item


logger = get_logger(__name__)


# Reserved on Windows, and a path separator on every platform. Control
# characters go with them: legal on Linux, and unopenable everywhere else.
_UNUSABLE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE = re.compile(r"\s+")
# Per segment rather than over the whole name, so that a long company does not
# eat the position it is printed next to.
SEGMENT_LIMIT = 60


def _path_segment(value: str) -> str:
    """
    Turn one part of a posting's name into something a filesystem will take.

    Args:
        value (str): A company or position name as it appears in the JD.

    Returns:
        str: The name with the unusable characters replaced and the length
            capped. Lossy on purpose: these segments are there to be read, and
            the id in front of them is what identifies the posting.
    """
    segment = _UNUSABLE.sub("-", value)

    return _WHITESPACE.sub(" ", segment).strip()[:SEGMENT_LIMIT]


def _filename_segment(value: str) -> str:
    """Turn a name or position into one lowercase, hyphen-separated segment."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return "-".join(re.findall(r"[a-z0-9]+", ascii_value.casefold()))


def resume_stem(
    connection: sqlite3.Connection, user_id: int, job_id: int
) -> str:
    """Return the shared filename stem for a candidate's posting resume."""
    row = connection.execute(
        """
        SELECT user.full_name, job.position_name
        FROM FactUser AS user
        JOIN FactJob AS job ON job.id = ?
        WHERE user.id = ?
        """,
        (job_id, user_id),
    ).fetchone()

    if row is None:
        raise ValueError(f"No candidate with id {user_id}.")

    full_name, position_name = row
    name = _filename_segment(full_name or f"user-{user_id}")
    position = _filename_segment(position_name)
    return "-".join(part for part in (name, position, "cv") if part)


def resume_paths(
    connection: sqlite3.Connection, user_id: int, job_id: int, resumes_dir: Path
) -> tuple[Path, Path, Path]:
    """Return the JSON, HTML and PDF paths for one candidate and posting."""
    out_dir = posting_dir(connection, job_id, resumes_dir)
    stem = resume_stem(connection, user_id, job_id)
    return (
        out_dir / f"{stem}.json",
        out_dir / f"{stem}.html",
        out_dir / f"{stem}.pdf",
    )


def posting_dir(connection: sqlite3.Connection, job_id: int, resumes_dir: Path) -> Path:
    """
    Name the folder every artifact of one posting is written into.

    Args:
        connection (sqlite3.Connection): Open connection to the candidate base.
        job_id (int): Posting the resume is written against.
        resumes_dir (Path): Root the per-posting folders live under.

    Returns:
        Path: The folder. Every stage derives it the same way rather than being
            handed it, so renaming a folder by hand only hides it from the run
            that would have reused it.

    Raises:
        ValueError: If no posting has that id. Raised here rather than left to
            the stage, since a resume for a posting that is not in the base
            would have nothing to be written against anyway.
    """
    row = connection.execute(
        """
        SELECT company.company_name, job.position_name
        FROM FactJob AS job
        LEFT JOIN DimCompany AS company ON company.id = job.company_id
        WHERE job.id = ?
        """,
        (job_id,),
    ).fetchone()

    if row is None:
        raise ValueError(f"No posting with id {job_id}.")

    # Joined rather than formatted, because company_id is nullable: a posting
    # that never got one is named without it instead of with a gap where it
    # would have gone.
    segments = [str(job_id)] + [_path_segment(value) for value in row if value]

    # Trailing dots and spaces are dropped silently on Windows, so a folder
    # created under one name would be looked for under another next stage. The
    # id in front also keeps the name off the reserved device names: 'CON' is
    # unusable as a folder, '7 - CON' is not.
    return resumes_dir / " - ".join(filter(None, segments)).rstrip(" .")


def write(user_id: int, job_id: int, resumes_dir: Path):
    """
    Write the resume document and save it.

    Args:
        user_id (int): Candidate the CV is for.
        job_id (int): Posting the CV is written against.
        resumes_dir (Path): Root the per-posting folders live under.
    """
    logger.info("Resume write starting: user_id=%s job_id=%s", user_id, job_id)
    llm_settings = LLMSettings.from_env("resume")
    with LLMClient(llm_settings) as llm_client:
        with RunLogger(
            "resume",
            "write",
            items_total=1,
            llm_settings=llm_settings,
        ) as run_log:
            json_path, _, _ = resume_paths(
                run_log.connection, user_id, job_id, resumes_dir
            )
            out_dir = json_path.parent
            out_dir.mkdir(parents=True, exist_ok=True)

            print(f"Writing a resume for user {user_id} against job {job_id}...")
            try:
                with record_item(out_dir.name) as item:
                    document = generate_resume(
                        run_log.connection, user_id, job_id, llm_client
                    )

                    item.produced("FactJob", job_id)

                    json_path.write_text(
                        document.model_dump_json(indent=2), encoding="utf-8"
                    )
                    out_path = json_path
            except Exception:
                run_log.items_failed = 1
                logger.exception("Resume write failed: user_id=%s job_id=%s", user_id, job_id)
                raise

            run_log.items_ok = 1

    print(f"\nWrote the resume for user {user_id} against job {job_id} to {out_path}.")
    logger.info("Resume write completed: output=%s", out_path)


def render(user_id: int, job_id: int, resumes_dir: Path):
    """
    Render a written resume document as HTML.

    Args:
        user_id (int): Candidate the CV is for.
        job_id (int): Posting the CV was written against.
        resumes_dir (Path): Root the per-posting folders live under.
    """
    logger.info("Resume render starting: user_id=%s job_id=%s", user_id, job_id)
    with RunLogger("resume", "render", items_total=1) as run_log:
        json_path, html_path, _ = resume_paths(
            run_log.connection, user_id, job_id, resumes_dir
        )
        out_dir = json_path.parent

        print(f"Rendering {json_path}...")
        try:
            # The same telemetry wrapper the model-calling stage uses, so its
            # call list stays empty. The entity columns stay null: the document
            # on disk may have been written against an older version of the
            # posting, and they would point at one this run never read.
            with record_item(out_dir.name):
                document = ResumeDocument.model_validate_json(
                    json_path.read_text(encoding="utf-8")
                )

                html_path.write_text(render_html(document), encoding="utf-8")
                out_path = html_path
        except Exception:
            run_log.items_failed = 1
            logger.exception("Resume render failed: user_id=%s job_id=%s", user_id, job_id)
            raise

        run_log.items_ok = 1

    print(f"\nRendered {json_path.name} into {out_path}.")
    logger.info("Resume render completed: output=%s", out_path)


def pdf(user_id: int, job_id: int, resumes_dir: Path):
    """
    Print a rendered resume page as a PDF.

    Args:
        user_id (int): Candidate the CV is for.
        job_id (int): Posting the CV was written against.
        resumes_dir (Path): Root the per-posting folders live under.
    """
    # Imported here rather than beside the others so that the stages before
    # this one keep running on a machine with no WeasyPrint and no Pango
    # installed. Printing is the only stage that needs either.
    from resume_generator.pdf import render_pdf

    logger.info("Resume PDF starting: user_id=%s job_id=%s", user_id, job_id)
    with RunLogger("resume", "pdf", items_total=1) as run_log:
        _, html_path, pdf_path = resume_paths(
            run_log.connection, user_id, job_id, resumes_dir
        )
        out_dir = html_path.parent

        print(f"Printing {html_path}...")
        try:
            # Wrapped like the render stage and null for the same reason.
            with record_item(out_dir.name):
                printed = render_pdf(html_path.read_text(encoding="utf-8"))

                pdf_path.write_bytes(printed.pdf)
                out_path = pdf_path
        except Exception:
            run_log.items_failed = 1
            logger.exception("Resume PDF failed: user_id=%s job_id=%s", user_id, job_id)
            raise

        run_log.items_ok = 1

    print(
        f"\nPrinted {html_path.name} into {out_path} "
        f"over {printed.page_count} page(s)."
    )
    logger.info("Resume PDF completed: output=%s pages=%s", out_path, printed.page_count)


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
    logger.info(
        "Resume pipeline requested: stages=%s user_id=%s job_id=%s",
        stages, args.user_id, args.job_id,
    )

    if "write" in stages:
        write(args.user_id, args.job_id, RESUMES_DIR)

    if "render" in stages:
        render(args.user_id, args.job_id, RESUMES_DIR)

    if "pdf" in stages:
        pdf(args.user_id, args.job_id, RESUMES_DIR)

    logger.info("Resume pipeline completed: stages=%s", stages)


if __name__ == "__main__":
    main()
