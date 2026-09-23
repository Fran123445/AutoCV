from pathlib import Path

from resume_etl import resume_paths, resume_stem


def test_resume_artifacts_use_candidate_and_position_name(seeded_db):
    seeded_db.execute(
        "INSERT INTO FactUser (id, full_name) VALUES (?, ?)",
        (1, "José Núñez"),
    )
    seeded_db.execute(
        "INSERT INTO DimCompany (id, company_name) VALUES (?, ?)",
        (1, "Acme"),
    )
    seeded_db.execute(
        """
        INSERT INTO FactJob (
            id, source, source_job_id, position_name, company_id,
            scrape_date, raw_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (7, "test", "job-7", "Senior Data/AI Engineer", 1, "2026-09-20", ""),
    )
    seeded_db.commit()

    expected_stem = "jose-nunez-senior-data-ai-engineer-cv"
    assert resume_stem(seeded_db, 1, 7) == expected_stem
    assert [path.name for path in resume_paths(seeded_db, 1, 7, Path("resumes"))] == [
        f"{expected_stem}.json",
        f"{expected_stem}.html",
        f"{expected_stem}.pdf",
    ]
