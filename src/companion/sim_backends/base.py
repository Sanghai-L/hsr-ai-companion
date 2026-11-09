"""Structured backend boundary, independent of any simulator dependency."""
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class BackendInput:
    build: dict
    stage: dict
    seed: int = 42
    mode: str = "roll"
    initial_sp: int = 3
    initial_energy_ratio: float = 0.5
    enemy_overrides: dict = field(default_factory=dict)

    def to_dict(self):
        from dataclasses import asdict
        return asdict(self)


class Backend(Protocol):
    def capabilities(self) -> dict: ...
    def compile(self, value: BackendInput, *, timeout: float = 30) -> dict: ...
    def execute(self, value: BackendInput, *, timeout: float = 30) -> dict: ...
