from db_creation import (
    _create_schema,
    _load_concept_dependencies,
    _load_concepts_data,
    _load_degree_translations_data,
    _load_degrees_data,
    _load_roles_data,
    _load_seniority_data,
    _load_technologies_data,
    _load_technology_concepts,
    _load_technology_dependencies,
)

import sqlite3

import pytest


@pytest.fixture
def db():
    """
    An empty in-memory database with foreign keys enforced.

    Function scoped: a ":memory:" base dies with its connection, so a fresh one
    per test costs almost nothing and buys total isolation between tests.
    """
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")

    yield conn

    conn.close()


@pytest.fixture
def seeded_db(db):
    """
    The schema with every registry loaded, committed.
    """
    _create_schema(db)
    _load_seniority_data(db)
    _load_roles_data(db)
    _load_degrees_data(db)
    _load_degree_translations_data(db)
    _load_technologies_data(db)
    _load_concepts_data(db)
    _load_technology_dependencies(db)
    _load_concept_dependencies(db)
    _load_technology_concepts(db)

    db.commit()

    return db
