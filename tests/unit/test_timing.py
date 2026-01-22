"""Unit tests for timing utilities."""

import time

from pfruleslawyer.core import TimingContext, optional_timing


class TestTimingContext:
    """Tests for TimingContext."""

    def test_record_stores_timing(self):
        """Test that record stores label and duration."""
        ctx = TimingContext()
        ctx.record("test_op", 123.45)
        assert len(ctx.timings) == 1
        assert ctx.timings[0] == ("test_op", 123.45)

    def test_measure_context_manager(self):
        """Test that measure context manager records duration."""
        ctx = TimingContext()
        with ctx.measure("sleep_test"):
            time.sleep(0.01)  # 10ms
        assert len(ctx.timings) == 1
        label, duration = ctx.timings[0]
        assert label == "sleep_test"
        assert duration >= 10  # At least 10ms (in milliseconds)

    def test_summary_format(self):
        """Test that summary produces expected format."""
        ctx = TimingContext()
        ctx.record("op1", 100.0)
        ctx.record("op2", 200.0)
        summary = ctx.summary()
        assert "op1: 100ms" in summary
        assert "op2: 200ms" in summary
        assert "Total: 300ms" in summary

    def test_as_dict(self):
        """Test that as_dict returns proper structure."""
        ctx = TimingContext()
        ctx.record("op1", 100.0)
        ctx.record("op2", 200.0)
        result = ctx.as_dict()
        assert "timings" in result
        assert "total_ms" in result
        assert len(result["timings"]) == 2
        assert result["total_ms"] == 300.0
        assert result["timings"][0] == {"label": "op1", "duration_ms": 100.0}


class TestOptionalTiming:
    """Tests for optional_timing helper."""

    def test_with_context_records_timing(self):
        """Test that optional_timing records when context is provided."""
        ctx = TimingContext()
        with optional_timing(ctx, "test"):
            time.sleep(0.01)
        assert len(ctx.timings) == 1
        assert ctx.timings[0][0] == "test"

    def test_without_context_is_noop(self):
        """Test that optional_timing is a no-op when context is None."""
        # Should not raise and should work as a no-op
        with optional_timing(None, "test"):
            x = 1 + 1
        assert x == 2
