import pytest

from monitor.domain import ResultStatus, SearchEvidence, TargetType
from monitor.search.registry import SearchRegistry


@pytest.mark.asyncio
async def test_occupied_result_short_circuits_secondary_methods() -> None:
    registry = SearchRegistry()
    calls = []

    async def resolver(client, username, target_type):
        calls.append("resolver")
        return SearchEvidence(ResultStatus.OCCUPIED, "resolver", "exact entity found")

    async def secondary(client, username, target_type):
        calls.append("secondary")
        return SearchEvidence(ResultStatus.INCONCLUSIVE, "search", "not needed")

    registry.register(resolver)
    registry.register(secondary)
    result = await registry.check(object(), "sample_name", TargetType.BOTH)

    assert result.status == ResultStatus.OCCUPIED
    assert calls == ["resolver"]


@pytest.mark.asyncio
async def test_apparent_availability_requires_secondary_search() -> None:
    registry = SearchRegistry()

    async def resolver(client, username, target_type):
        return SearchEvidence(ResultStatus.APPARENTLY_AVAILABLE, "resolver", "not occupied")

    async def secondary(client, username, target_type):
        return SearchEvidence(ResultStatus.INCONCLUSIVE, "search", "no exact match")

    registry.register(resolver)
    registry.register(secondary)
    result = await registry.check(object(), "sample_name", TargetType.BOTH)

    assert result.status == ResultStatus.APPARENTLY_AVAILABLE
    assert "not a guarantee" in result.details


@pytest.mark.asyncio
async def test_secondary_exact_match_overrides_availability() -> None:
    registry = SearchRegistry()

    async def resolver(client, username, target_type):
        return SearchEvidence(ResultStatus.APPARENTLY_AVAILABLE, "resolver", "not occupied")

    async def secondary(client, username, target_type):
        return SearchEvidence(ResultStatus.OCCUPIED, "search", "exact match")

    registry.register(resolver)
    registry.register(secondary)
    result = await registry.check(object(), "sample_name", TargetType.BOTH)

    assert result.status == ResultStatus.OCCUPIED
    assert result.method == "search"
