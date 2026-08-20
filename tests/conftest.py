"""Shared pytest fixtures. Everything here runs offline against an in-memory database."""

import pytest

from canary import db


@pytest.fixture
def conn():
    """A fresh in-memory database with the schema applied."""
    connection = db.init_db(":memory:")
    yield connection
    connection.close()
