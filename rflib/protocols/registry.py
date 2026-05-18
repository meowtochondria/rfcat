from typing import Dict, List
from .base import Protocol

from .princeton import subghz_protocol_princeton, PrincetonProtocol
from .gate_tx import subghz_protocol_gate_tx, GateTXProtocol


PROTOCOL_REGISTRY: Dict[str, Protocol] = {
    subghz_protocol_princeton.name: subghz_protocol_princeton,
    subghz_protocol_gate_tx.name: subghz_protocol_gate_tx,
}

PROTOCOL_LIST: List[Protocol] = [
    subghz_protocol_princeton,
    subghz_protocol_gate_tx,
]


def get_protocol(name: str) -> Protocol | None:
    return PROTOCOL_REGISTRY.get(name)


def list_protocols() -> List[str]:
    return list(PROTOCOL_REGISTRY.keys())


__all__ = [
    'Protocol',
    'PROTOCOL_REGISTRY',
    'PROTOCOL_LIST',
    'get_protocol',
    'list_protocols',
    'subghz_protocol_princeton',
    'subghz_protocol_gate_tx',
    'PrincetonProtocol',
    'GateTXProtocol',
]