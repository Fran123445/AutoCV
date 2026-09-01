from etl.projects.load import load


def make_project(
    *,
    path="C:/repos/demo",
    task_desc="Built the first version.",
    technologies=("python",),
    concepts=("agile",),
    head_commit="first-head",
    first_commit_at="2024-01-01",
    last_commit_at="2024-02-01",
    technology_descriptions=None,
    concept_descriptions=None,
):
    return {
        "path": path,
        "head_commit": head_commit,
        "first_commit_at": first_commit_at,
        "last_commit_at": last_commit_at,
        "technologies": {"technologies": list(technologies)},
        "narrative": {"task_desc": task_desc, "concepts": list(concepts)},
        "descriptions": {
            "technologies": technology_descriptions or [],
            "concepts": concept_descriptions or [],
        },
    }


def test_reloading_a_project_replaces_metadata_and_evidence(seeded_db):
    first = make_project(
        technology_descriptions=[{"name": "python", "descr": "old role"}],
        concept_descriptions=[{"name": "agile", "descr": "old approach"}],
    )
    project_id = load(first, seeded_db)

    second = make_project(
        task_desc="Built the revised version.",
        technologies=("javascript",),
        concepts=("scrum",),
        head_commit="second-head",
        first_commit_at="2024-01-02",
        last_commit_at="2024-03-01",
        technology_descriptions=[{"name": "javascript", "descr": "new role"}],
        concept_descriptions=[{"name": "scrum", "descr": "new approach"}],
    )
    reloaded_id = load(second, seeded_db)

    assert reloaded_id == project_id
    project = seeded_db.execute(
        """
        SELECT task_desc, head_commit, first_commit_at, last_commit_at
        FROM Project
        WHERE id = ?
        """,
        (project_id,),
    ).fetchone()
    assert project == (
        "Built the revised version.",
        "second-head",
        "2024-01-02",
        "2024-03-01",
    )

    technologies = seeded_db.execute(
        """
        SELECT dt.name, pt.descr
        FROM ProjectTechnologies pt
        JOIN DimTechnologies dt ON dt.id = pt.technology_id
        WHERE pt.project_id = ?
        """,
        (project_id,),
    ).fetchall()
    concepts = seeded_db.execute(
        """
        SELECT dc.concept_name, pc.descr
        FROM ProjectConcepts pc
        JOIN DimConcepts dc ON dc.id = pc.concept_id
        WHERE pc.project_id = ?
        """,
        (project_id,),
    ).fetchall()

    assert technologies == [("javascript", "new role")]
    assert concepts == [("scrum", "new approach")]
