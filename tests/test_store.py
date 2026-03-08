import pytest

from app.store import CMDBStore, generate_records


@pytest.mark.asyncio
async def test_mutation_cap_is_enforced() -> None:
    store = CMDBStore(
        records=generate_records(20, seed=1),
        max_record_changes_per_hour=3,
        seed=1,
    )
    mutated = await store.mutate_once(10)
    assert mutated == 3

    mutated_again = await store.mutate_once(10)
    assert mutated_again == 0

