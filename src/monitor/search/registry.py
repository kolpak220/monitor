from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from monitor.domain import ResultStatus, SearchEvidence, TargetType
from monitor.search.resolver import resolve_username
from monitor.search.substring import search_username

SearchMethod = Callable[[Any, str, TargetType], Awaitable[SearchEvidence]]


class SearchRegistry:
    def __init__(self) -> None:
        self._methods: list[SearchMethod] = []

    def register(self, method: SearchMethod) -> None:
        self._methods.append(method)

    async def check(self, client: Any, username: str, target_type: TargetType) -> SearchEvidence:
        if not self._methods:
            raise RuntimeError("No username search methods are registered")

        evidence: list[SearchEvidence] = []
        for method in self._methods:
            result = await method(client, username, target_type)
            evidence.append(result)

            if result.status in {
                ResultStatus.OCCUPIED,
                ResultStatus.COLLECTIBLE,
                ResultStatus.INVALID,
            }:
                return result

        resolver_result = evidence[0]
        if resolver_result.status == ResultStatus.APPARENTLY_AVAILABLE:
            secondary = evidence[-1] if len(evidence) > 1 else None
            if secondary and secondary.status == ResultStatus.OCCUPIED:
                return secondary
            return SearchEvidence(
                ResultStatus.APPARENTLY_AVAILABLE,
                "contacts.resolveUsername + contacts.search",
                (
                    "Exact resolution reported USERNAME_NOT_OCCUPIED and the secondary "
                    "search found no exact match. This is not a guarantee that Telegram "
                    "will allow registration or assignment."
                ),
            )

        return SearchEvidence(
            ResultStatus.INCONCLUSIVE,
            " + ".join(item.method for item in evidence),
            "Telegram did not provide enough evidence to classify this username.",
        )


def build_registry() -> SearchRegistry:
    registry = SearchRegistry()
    registry.register(resolve_username)
    registry.register(search_username)
    return registry
