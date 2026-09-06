"""Print a rendered resume page as PDF.

Every rule that governs where a page breaks and how wide its margins are is
already in templates/resume.css, and WeasyPrint lays the page out from there.
"""

from typing import NamedTuple

from weasyprint import HTML

from app_log import get_logger


logger = get_logger(__name__)


class PrintedResume(NamedTuple):
    """
    One printed document and the paper it takes.

    Attributes:
        pdf (bytes): The document itself.
        page_count (int): How many pages it came out to. A resume that runs to
            three is a problem with the writing rather than the printing, and
            the count is the only place in the pipeline where that shows.
    """

    pdf: bytes
    page_count: int


def render_pdf(html: str) -> PrintedResume:
    """
    Print one rendered resume page as a PDF document.

    Args:
        html (str): The page produced by render_html.

    Returns:
        PrintedResume: The document and its page count.
    """
    # Laying the page out and serialising it are split so that the count comes
    # off the same pass that produces the bytes. Calling write_pdf on the HTML
    # directly would return the document without it, and asking afterwards
    # would lay the whole thing out a second time.
    #
    # No base_url either: the page inlines its stylesheet and links no images,
    # so there is no relative reference left for WeasyPrint to resolve.
    logger.info("Rendering resume PDF: html_characters=%s", len(html))
    document = HTML(string=html).render()

    pdf = document.write_pdf()
    result = PrintedResume(pdf=pdf, page_count=len(document.pages))
    logger.info("Resume PDF rendered: bytes=%s pages=%s", len(pdf), result.page_count)
    return result
