"""Localizable text and formatting for generated resume documents."""

from dataclasses import dataclass
from collections.abc import Mapping


@dataclass(frozen=True)
class ResumeLabels:
    """Structural labels printed by the resume template."""

    summary: str
    skills: str
    experience: str
    projects: str
    education: str
    languages: str
    gpa: str


@dataclass(frozen=True)
class ResumeLocale:
    """The language-specific pieces shared by writing and rendering."""

    code: str
    llm_name: str
    labels: ResumeLabels
    months: tuple[str, ...]
    present: str
    language_names: Mapping[str, str]
    proficiency_levels: Mapping[str, str]


LOCALES = {
    "en": ResumeLocale(
        code="en",
        llm_name="English",
        labels=ResumeLabels(
            summary="Summary",
            skills="Skills",
            experience="Experience",
            projects="Personal Projects",
            education="Education",
            languages="Languages",
            gpa="GPA",
        ),
        months=(
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        ),
        present="Present",
        language_names={
            "english": "English",
            "inglés": "English",
            "spanish": "Spanish",
            "español": "Spanish",
            "french": "French",
            "francés": "French",
            "german": "German",
            "alemán": "German",
            "italian": "Italian",
            "italiano": "Italian",
            "portuguese": "Portuguese",
            "portugués": "Portuguese",
        },
        proficiency_levels={
            "native": "Native",
            "nativo": "Native",
            "fluent": "Fluent",
            "fluido": "Fluent",
            "advanced": "Advanced",
            "avanzado": "Advanced",
            "intermediate": "Intermediate",
            "intermedio": "Intermediate",
            "basic": "Basic",
            "básico": "Basic",
            "beginner": "Beginner",
            "principiante": "Beginner",
        },
    ),
    "es": ResumeLocale(
        code="es",
        llm_name="Spanish",
        labels=ResumeLabels(
            summary="Resumen",
            skills="Habilidades",
            experience="Experiencia",
            projects="Proyectos personales",
            education="Educación",
            languages="Idiomas",
            gpa="Promedio",
        ),
        months=(
            "ene", "feb", "mar", "abr", "may", "jun",
            "jul", "ago", "sep", "oct", "nov", "dic",
        ),
        present="Actualidad",
        language_names={
            "english": "Inglés",
            "inglés": "Inglés",
            "spanish": "Español",
            "español": "Español",
            "french": "Francés",
            "francés": "Francés",
            "german": "Alemán",
            "alemán": "Alemán",
            "italian": "Italiano",
            "italiano": "Italiano",
            "portuguese": "Portugués",
            "portugués": "Portugués",
        },
        proficiency_levels={
            "native": "Nativo",
            "nativo": "Nativo",
            "fluent": "Fluido",
            "fluido": "Fluido",
            "advanced": "Avanzado",
            "avanzado": "Avanzado",
            "intermediate": "Intermedio",
            "intermedio": "Intermedio",
            "basic": "Básico",
            "básico": "Básico",
            "beginner": "Principiante",
            "principiante": "Principiante",
        },
    ),
}

DEFAULT_LOCALE = LOCALES["en"]


def resolve_locale(language: str | None) -> ResumeLocale:
    """Return the supported locale for a stored language code."""

    return LOCALES.get((language or "").casefold(), DEFAULT_LOCALE)


def localize_language_name(name: str, language: str | None) -> str:
    """Translate a known spoken-language name for the resume locale."""

    locale = resolve_locale(language)
    return locale.language_names.get(name.casefold(), name)


def localize_proficiency_level(level: str, language: str | None) -> str:
    """Translate a known spoken-language proficiency for the resume locale."""

    locale = resolve_locale(language)
    return locale.proficiency_levels.get(level.casefold(), level)
