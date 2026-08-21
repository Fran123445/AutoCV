import pytest

from etl.dims import (
    UnknownSeedValue,
    solve_company_name_id,
    solve_concept_name_id,
    solve_degree_id,
    solve_role_id,
    solve_technology_name_id,
)


# The names asserted on are real seed entries. Each is the first row its loader
# writes, so it is stable as long as the seed file keeps that entry at all; the
# id it lands on is not, which is why every test reads back the name, never the id.


# --------------------------------------------------------------------------
# solve_company_name_id, the one dimension with no seed
# --------------------------------------------------------------------------

def name_of(seeded_db, table, column, dim_id):
    """Read a dimension id back as its canonical name."""
    if dim_id is None:
        return None

    row = seeded_db.execute(
        f"SELECT {column} FROM {table} WHERE id = ?", (dim_id,)
    ).fetchone()

    return row[0] if row else None


def test_a_new_company_is_inserted_and_its_id_returned(seeded_db):
    """Companies arrive with postings, so a missing name is created, not rejected."""
    solved = solve_company_name_id(seeded_db, "Acme")

    assert name_of(seeded_db, "DimCompany", "company_name", solved) == "Acme"


def test_the_same_company_twice_resolves_to_one_row(seeded_db):
    """
    ON CONFLICT DO NOTHING plus a follow-up SELECT: the second call must return
    the first call's id rather than insert a duplicate.
    """
    first = solve_company_name_id(seeded_db, "Acme")
    second = solve_company_name_id(seeded_db, "Acme")

    assert first == second
    assert seeded_db.execute(
        "SELECT count(*) FROM DimCompany WHERE company_name = ?", ("Acme",)
    ).fetchone()[0] == 1


def test_a_company_name_of_none_is_none(seeded_db):
    assert solve_company_name_id(seeded_db, None) is None


# --------------------------------------------------------------------------
# solve_role_id / solve_degree_id, seeded and nullable
# --------------------------------------------------------------------------

def test_a_seeded_role_resolves_to_its_row(seeded_db):
    solved = solve_role_id(seeded_db, "backend dev")

    assert name_of(seeded_db, "DimRole", "role_name", solved) == "backend dev"


def test_a_role_name_of_none_is_none(seeded_db):
    assert solve_role_id(seeded_db, None) is None


def test_an_unseeded_role_raises(seeded_db):
    with pytest.raises(UnknownSeedValue):
        solve_role_id(seeded_db, "not a real role")


def test_a_seeded_degree_resolves_to_its_row(seeded_db):
    solved = solve_degree_id(seeded_db, "computer science")

    assert name_of(seeded_db, "DimDegree", "name", solved) == "computer science"


def test_a_degree_name_of_none_is_none(seeded_db):
    assert solve_degree_id(seeded_db, None) is None


def test_an_unseeded_degree_raises(seeded_db):
    with pytest.raises(UnknownSeedValue):
        solve_degree_id(seeded_db, "underwater basket weaving")


# --------------------------------------------------------------------------
# solve_technology_name_id / solve_concept_name_id, seeded and not nullable
# --------------------------------------------------------------------------

def test_a_seeded_technology_resolves_to_its_row(seeded_db):
    solved = solve_technology_name_id(seeded_db, "python")

    assert name_of(seeded_db, "DimTechnologies", "name", solved) == "python"


def test_an_unseeded_technology_raises(seeded_db):
    """
    No None branch here: unlike role and degree, a technology name is never
    optional by the time it reaches load, so an absent row is always an error.
    """
    with pytest.raises(UnknownSeedValue):
        solve_technology_name_id(seeded_db, "cobol-on-cogs")


def test_a_seeded_concept_resolves_to_its_row(seeded_db):
    solved = solve_concept_name_id(seeded_db, "agile")

    assert name_of(seeded_db, "DimConcepts", "concept_name", solved) == "agile"


def test_an_unseeded_concept_raises(seeded_db):
    with pytest.raises(UnknownSeedValue):
        solve_concept_name_id(seeded_db, "vibes-driven design")
