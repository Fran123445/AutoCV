"""Print a resume document as HTML.

Every layout decision lives in templates/resume.html; this module only hands
that template a document and the stylesheet it inlines. It is kept out of
generator so that building a document and printing one stay separable: a caller
after the structure alone never pays for the template engine, and the PDF pass
described on the template is one more caller of the string produced here rather
than a second layout.
"""

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import TEMPLATES_DIR

from .dates import span
from .localization import (
    localize_language_name,
    localize_proficiency_level,
    resolve_locale,
)
from .models import ResumeDocument


TEMPLATE_NAME = "resume.html"
STYLESHEET_NAME = "resume.css"

# Built once and reused. trim_blocks and lstrip_blocks only tidy the emitted
# whitespace; without them the page renders the same but is unreadable when
# opened as source.
_environment = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)
# Registered as a global rather than a filter: the template calls it on two
# arguments, and a filter reading its second from a pipe would only obscure that.
_environment.globals["span"] = span
_environment.globals["spoken_language_name"] = localize_language_name
_environment.globals["spoken_language_level"] = localize_proficiency_level


def render_html(document: ResumeDocument) -> str:
    """
    Render one resume document as a self-contained HTML page.

    Args:
        document (ResumeDocument): The resume to print.

    Returns:
        str: The page, carrying its own styling so that the file survives being
            moved and the PDF pass fetches nothing.
    """
    stylesheet = (TEMPLATES_DIR / STYLESHEET_NAME).read_text(encoding="utf-8")
    locale = resolve_locale(document.language)

    return _environment.get_template(TEMPLATE_NAME).render(
        document=document,
        locale=locale,
        labels=locale.labels,
        stylesheet=stylesheet,
    )
