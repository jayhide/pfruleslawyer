"""Timing utilities for instrumenting operations."""

import time
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class TimingContext:
    """Accumulates timing data across multiple operations."""

    timings: list[tuple[str, float]] = field(default_factory=list)

    def record(self, label: str, duration_ms: float) -> None:
        """Record a timing measurement."""
        self.timings.append((label, duration_ms))

    @contextmanager
    def measure(self, label: str) -> Iterator[None]:
        """Context manager to measure duration of a block."""
        start = time.perf_counter()
        yield
        duration_ms = (time.perf_counter() - start) * 1000
        self.record(label, duration_ms)

    def summary(self) -> str:
        """Return a formatted summary of all timings."""
        lines = [f"  {label}: {dur:.0f}ms" for label, dur in self.timings]
        total = sum(dur for _, dur in self.timings)
        lines.append(f"  Total: {total:.0f}ms")
        return "\n".join(lines)

    def as_dict(self) -> dict:
        """Return timings as a dict for JSON serialization."""
        return {
            "timings": [{"label": label, "duration_ms": dur} for label, dur in self.timings],
            "total_ms": sum(dur for _, dur in self.timings),
        }


def optional_timing(ctx: TimingContext | None, label: str):
    """Return a timing context manager if ctx is provided, else a no-op."""
    if ctx is not None:
        return ctx.measure(label)
    return nullcontext()
