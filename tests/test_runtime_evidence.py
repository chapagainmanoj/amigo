"""Runtime evidence summarizer tests."""

from scripts.summarize_runtime_evidence import summarize


def test_summarizer_reports_nearest_rank_latency_without_message_content():
    lines = [
        "database_operation=get_dashboard_snapshot outcome=ok duration_ms=10.000",
        "sensitive participant message that must not survive",
        "database_operation=get_dashboard_snapshot outcome=error duration_ms=30.000",
        "database_operation=claim_reminder_for_send outcome=ok duration_ms=20.000",
        "event_loop_delay_ms=2.000",
        "event_loop_delay_ms=8.000",
    ]

    result = summarize(lines)

    assert result["database"]["overall"] == {
        "count": 3,
        "p50_ms": 20.0,
        "p95_ms": 30.0,
        "max_ms": 30.0,
    }
    assert result["database"]["operations"]["get_dashboard_snapshot"]["errors"] == 1
    assert result["event_loop"] == {
        "count": 2,
        "p50_ms": 2.0,
        "p95_ms": 8.0,
        "max_ms": 8.0,
    }
    assert "sensitive" not in repr(result)


def test_summarizer_preserves_unknown_when_no_measurements_exist():
    result = summarize(["ordinary unrelated log line"])

    assert result["database"]["overall"] == {
        "count": 0,
        "p50_ms": None,
        "p95_ms": None,
        "max_ms": None,
    }
    assert result["event_loop"]["count"] == 0
