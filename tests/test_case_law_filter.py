from src.ingest.case_law import filter_mietrecht_decisions


def _row(content: str) -> dict:
    return {"id": content[:8], "markdown_content": content}


def test_filter_keeps_decisions_citing_mietrecht_bgb_sections():
    rows = [
        _row("Der Anspruch folgt aus § 535 BGB."),
        _row("Es geht um Strafrecht, § 242 StGB."),
    ]
    kept, report = filter_mietrecht_decisions(rows, max_decisions=10)
    assert len(kept) == 1
    assert kept[0]["markdown_content"].startswith("Der Anspruch")
    assert report["total"] == 2
    assert report["regex_matches"] == 1
    assert report["relevant"] == 1
    assert report["kept"] == 1


def test_filter_keeps_decisions_citing_related_statutes():
    rows = [_row("Die Umlage richtet sich nach § 2 BetrKV.")]
    kept, report = filter_mietrecht_decisions(rows, max_decisions=10)
    assert len(kept) == 1
    assert report["regex_matches"] == 1
    assert report["relevant"] == 1


def test_filter_drops_single_keyword_hit_without_citation():
    rows = [_row("Die Mietminderung war hier strittig.")]
    kept, report = filter_mietrecht_decisions(rows, max_decisions=10)
    assert kept == []
    assert report["keyword_matches"] == 1
    assert report["regex_matches"] == 0
    assert report["relevant"] == 0


def test_filter_keeps_decisions_with_multiple_keyword_hits():
    rows = [_row("Streitig waren Mietminderung, Nebenkosten und Kündigung.")]
    kept, report = filter_mietrecht_decisions(rows, max_decisions=10)
    assert len(kept) == 1
    assert report["keyword_matches"] == 1
    assert report["regex_matches"] == 0
    assert report["relevant"] == 1


def test_filter_drops_irrelevant_decisions():
    rows = [_row("Es ging um einen Verkehrsunfall und Schadensersatz nach § 823 BGB.")]
    kept, report = filter_mietrecht_decisions(rows, max_decisions=10)
    assert kept == []
    assert report["relevant"] == 0


def test_filter_always_keeps_all_regex_matches_regardless_of_cap():
    rows = [
        _row("Der Anspruch folgt aus § 558 BGB."),
        _row("Auch hier: § 562 BGB."),
        _row("Streitig waren Mietminderung, Nebenkosten und Kündigung."),
    ]
    kept, report = filter_mietrecht_decisions(rows, max_decisions=0)
    assert len(kept) == 2
    assert all("BGB" in r["markdown_content"] for r in kept)
    assert report["regex_matches"] == 2
    assert report["relevant"] == 3
    assert report["kept"] == 2


def test_filter_caps_keyword_only_tier_by_density():
    rows = [
        _row("Streitig waren Mietminderung und Nebenkosten."),
        _row("Streitig waren Mietminderung, Nebenkosten, Kündigung und Kaution."),
    ]
    kept, report = filter_mietrecht_decisions(rows, max_decisions=1)
    assert len(kept) == 1
    assert "Kaution" in kept[0]["markdown_content"]
    assert report["regex_matches"] == 0
    assert report["relevant"] == 2
    assert report["kept"] == 1


def test_filter_handles_missing_markdown_content():
    rows = [{"id": "no-content"}]
    kept, report = filter_mietrecht_decisions(rows, max_decisions=10)
    assert kept == []
    assert report["total"] == 1
