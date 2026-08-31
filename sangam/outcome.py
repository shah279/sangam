"""Small, shared result type for observable pipeline stages."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StageResult:
    stage: str
    count: int = 0
    processed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error_summary(self, limit: int = 20) -> str | None:
        if not self.errors:
            return None
        shown = self.errors[:limit]
        suffix = f"\n... and {len(self.errors) - limit} more" if len(self.errors) > limit else ""
        return "\n".join(shown) + suffix
