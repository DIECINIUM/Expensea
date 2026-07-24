"""Source connector contracts and built-in adapter registry."""

from app.connectors.contracts import (
    Connector,
    ConnectorBatch,
    ConnectorDescriptor,
    ConnectorEnvelope,
    ConnectorHealth,
)
from app.connectors.registry import ConnectorRegistry

__all__ = [
    "Connector",
    "ConnectorBatch",
    "ConnectorDescriptor",
    "ConnectorEnvelope",
    "ConnectorHealth",
    "ConnectorRegistry",
]
