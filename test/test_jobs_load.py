import sqlite3

import pytest

from etl.dims import solve_seniority_id


def label_of(connection: sqlite3.Connection, seniority_id: int | None) -> str | None:
    """
    Read a DimSeniority id back as its label.

    The ids are autoincrement and depend on the order seeds/seniority.json
    happens to list its entries, so asserting on them directly would tie these
    tests to the seed file's ordering. The label is the stable identity.
    """
    if seniority_id is None:
        return None

    row = connection.execute(
        "SELECT label FROM DimSeniority WHERE id = ?", (seniority_id,)
    ).fetchone()

    return row[0] if row else None


# --------------------------------------------------------------------------
# solve_seniority_id, when the posting names a level
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "label", ["trainee", "junior", "ssr", "senior", "lead"]
)
def test_a_named_level_resolves_to_its_own_row(seeded_db, label):
    solved = solve_seniority_id(seeded_db, label, None)

    assert label_of(seeded_db, solved) == label


def test_the_label_wins_over_the_years(seeded_db):
    """
    The year fallback is only consulted when there is no label. A posting that
    says "Senior" and then asks for 1 year of experience is describing the role
    it wants, badly, and the word is still what it called the role.
    """
    solved = solve_seniority_id(seeded_db, "senior", 1)

    assert label_of(seeded_db, solved) == "senior"


# --------------------------------------------------------------------------
# solve_seniority_id, when the posting only states years
# --------------------------------------------------------------------------

@pytest.mark.parametrize("min_experience, expected", [
    # Both trainee (0-1) and junior (0-2) cover 0. The narrower range wins,
    # which is the tiebreak that keeps an unqualified "no experience needed"
    # out of junior.
    (0, "trainee"),
    # Past trainee's upper bound, inside junior's.
    (1, "junior"),
    # The half-open boundary: junior ends at 2 and ssr starts there, so 2 reads
    # as the higher of the two adjacent labels rather than the lower.
    (2, "ssr"),
    (3, "ssr"),
    (4, "ssr"),
    # Same boundary rule one level up: ssr ends at 5, senior starts there.
    (5, "senior"),
    (6, "senior"),
    # Both senior (5+) and lead (7+) are open ended and both cover 7. Ordering
    # sends it to senior, which is the point of the fallback: lead is a claim
    # about responsibility, and a posting that means it says the word.
    (7, "senior"),
    (20, "senior"),
], ids=[
    "zero_is_trainee_not_junior",
    "one",
    "two_is_ssr_not_junior",
    "three", "four",
    "five_is_senior_not_ssr",
    "six",
    "seven_is_senior_not_lead",
    "many_years",
])
def test_years_fall_back_to_the_label_covering_them(
    seeded_db, min_experience, expected
):
    solved = solve_seniority_id(seeded_db, None, min_experience)

    assert label_of(seeded_db, solved) == expected

# --------------------------------------------------------------------------
# solve_seniority_id, when the posting states neither
# --------------------------------------------------------------------------

def test_neither_a_label_nor_years_is_none(seeded_db):
    assert solve_seniority_id(seeded_db, None, None) is None
