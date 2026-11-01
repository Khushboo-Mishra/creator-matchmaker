import inspect

import pytest


@pytest.fixture
def synthetic_migration_compatibility(monkeypatch):
    """Test historical migration mechanics with synthetic compatible inputs only.

    Production hashes remain pinned: changed live comment sampling must reject
    old checkpoints (covered separately in test_current_audience).
    """
    from src import migrate_checkpoint as migration
    from src.providers import LiveProvider

    monkeypatch.setitem(
        migration.COLLECTION_METHODS,
        "comments",
        migration.sha(inspect.getsource(LiveProvider.comments)),
    )
