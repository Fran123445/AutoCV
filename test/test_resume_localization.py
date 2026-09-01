from resume_generator.dates import span
from resume_generator.generator import _build_education
from resume_generator.localization import resolve_locale
from resume_generator.models import (
    ResumeDocument,
    ResumeEducation,
    ResumeExperience,
    ResumeLanguage,
    ResumeProfile,
    ResumeProject,
    ResumeSkillGroup,
)
from resume_generator.render import render_html
from llm.tasks.resume.models import ResumePromptContext
from llm.tasks.resume.write import write_resume


def make_document(language="es"):
    return ResumeDocument(
        language=language,
        profile=ResumeProfile(full_name="Ada Lovelace"),
        summary=["Diseño sistemas de datos."],
        skills=[ResumeSkillGroup(label="Datos", items=["Python"])],
        experience=[
            ResumeExperience(
                company="Analytical Engines",
                role="Data Engineer",
                start_date="2024-01",
                bullets=["Construí un pipeline."],
            )
        ],
        projects=[ResumeProject(title="Proyecto de datos", bullets=["Construí un modelo."])],
        education=[
            ResumeEducation(
                degree="Ingeniería",
                institution="Universidad",
                gpa="9",
                start_date="2020-03",
                end_date="2024-12",
            )
        ],
        languages=[
            ResumeLanguage(name="Spanish", level="Native"),
            ResumeLanguage(name="English", level="C1"),
        ],
    )


def test_span_localizes_spanish_months_and_ongoing_text():
    assert span("2024-01", None, "es") == "ene 2024 - Actualidad"


def test_span_defaults_to_english_for_existing_callers():
    assert span("2024-01", None) == "Jan 2024 - Present"


def test_spanish_resume_localizes_structural_text():
    html = render_html(make_document())

    assert '<html lang="es">' in html
    for heading in (
        "Resumen",
        "Habilidades",
        "Experiencia",
        "Proyectos personales",
        "Educación",
        "Idiomas",
    ):
        assert f"<h2>{heading}</h2>" in html
    assert "ene 2024 - Actualidad" in html
    assert "Promedio 9" in html
    assert "<strong>Español</strong> — Nativo" in html
    assert "<strong>Inglés</strong> — C1" in html


def test_degree_names_use_the_requested_translation(seeded_db):
    seeded_db.execute(
        "INSERT INTO FactUser (id, full_name) VALUES (?, ?)",
        (1, "Ada Lovelace"),
    )
    degree_id = seeded_db.execute(
        "SELECT id FROM DimDegree WHERE name = ?",
        ("information systems engineering",),
    ).fetchone()[0]
    seeded_db.execute(
        """
        INSERT INTO UserEducation (user_id, degree_id, institution)
        VALUES (?, ?, ?)
        """,
        (1, degree_id, "Universidad"),
    )

    education = _build_education(seeded_db, 1, "es")

    assert education[0].degree == "Ingeniería en Sistemas"

    education = _build_education(seeded_db, 1, "en")

    assert education[0].degree == "Information Systems Engineering"


def test_degree_names_fall_back_to_english(seeded_db):
    seeded_db.execute(
        "INSERT INTO FactUser (id, full_name) VALUES (?, ?)",
        (1, "Ada Lovelace"),
    )
    degree_id = seeded_db.execute(
        "SELECT id FROM DimDegree WHERE name = ?",
        ("information systems engineering",),
    ).fetchone()[0]
    seeded_db.execute(
        "INSERT INTO UserEducation (user_id, degree_id, institution) VALUES (?, ?, ?)",
        (1, degree_id, "Universidad"),
    )
    seeded_db.execute(
        "DELETE FROM DimDegreeTranslation WHERE degree_id = ? AND locale = ?",
        (degree_id, "es"),
    )

    education = _build_education(seeded_db, 1, "es")

    assert education[0].degree == "Information Systems Engineering"


def test_unknown_resume_language_falls_back_to_english():
    assert resolve_locale(None).code == "en"
    assert resolve_locale("fr").code == "en"

    html = render_html(make_document("fr"))

    assert '<html lang="en">' in html
    assert "<h2>Summary</h2>" in html
    assert "Jan 2024 - Present" in html


def test_writer_uses_the_same_resolved_language():
    captured = {}

    class FakeLLMClient:
        def post_chat(self, prompt, schema, task_name):
            captured["prompt"] = prompt
            return {
                "summary": [],
                "skills": [],
                "work_bullets": [],
                "personal_bullets": [],
            }

    write_resume(
        ResumePromptContext(job_description="Descripción", language="es"),
        FakeLLMClient(),
    )

    assert "every generated field in Spanish" in captured["prompt"]
