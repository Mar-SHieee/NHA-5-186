from scripts.spikes.joern.audit_joern_spike import _write_report_preserving_triage


def test_generated_spike_report_keeps_triage_addendum(tmp_path):
    report = tmp_path / "joern_spike.md"
    triage = "<!-- TRIAGE:BEGIN -->\n## Triage\n<!-- TRIAGE:END -->\n"
    report.write_text(f"old report\n\n{triage}", encoding="utf-8")

    _write_report_preserving_triage(report, "new report\n")

    assert report.read_text(encoding="utf-8") == f"new report\n\n{triage}"
