"""Versioned municipal context; never substitutes city data for a parcel review."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def pickering_context() -> dict:
    return json.loads((Path(__file__).parent.parent / 'data' / 'pickering.json').read_text(encoding='utf-8'))


def is_pickering(name: str) -> bool:
    return name in ('Pickering', 'Pickering (Dunbarton)')
