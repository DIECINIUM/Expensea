"""Explicit connector registry for built-in and future source adapters."""

from collections.abc import Iterable

from app.connectors.contracts import Connector, ConnectorDescriptor
from app.domain.enums import ConnectorType
from app.ingestion.errors import IngestionConflictError


class ConnectorRegistry:
    """Resolve adapters by a stable key without provider conditionals."""

    def __init__(self, connectors: Iterable[Connector] = ()) -> None:
        self._connectors: dict[ConnectorType, Connector] = {}
        for connector in connectors:
            self.register(connector)

    def register(self, connector: Connector) -> None:
        key = connector.descriptor.key
        if key in self._connectors:
            raise IngestionConflictError(
                code="CONNECTOR_ALREADY_REGISTERED",
                message=f"Connector {key.value} is already registered.",
            )
        self._connectors[key] = connector

    def get(self, key: ConnectorType) -> Connector:
        try:
            return self._connectors[key]
        except KeyError as exc:
            raise IngestionConflictError(
                code="CONNECTOR_NOT_REGISTERED",
                message=f"Connector {key.value} is not registered.",
            ) from exc

    def descriptors(self) -> tuple[ConnectorDescriptor, ...]:
        return tuple(
            connector.descriptor
            for _, connector in sorted(
                self._connectors.items(),
                key=lambda item: item[0].value,
            )
        )
