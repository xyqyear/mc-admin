import pytest

from app.operations.journal import OperationJournal


@pytest.fixture
def journal(db_session_factory):
    return OperationJournal(db_session_factory)
