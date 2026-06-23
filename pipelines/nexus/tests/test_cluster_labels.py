"""Tests for the cluster_labels asset pure helpers."""

from nexus.assets.ml.cluster_labels import build_label_prompt, parse_label_response

# ---------------------------------------------------------------------------
# build_label_prompt
# ---------------------------------------------------------------------------


def test_build_label_prompt_contains_cluster_id() -> None:
    prompt = build_label_prompt("c_42", ["photonic", "silicon"], ["A paper on EUV"])
    assert "c_42" in prompt


def test_build_label_prompt_contains_top_terms() -> None:
    prompt = build_label_prompt("c_0", ["photonic", "waveguide", "silicon"], [])
    assert "photonic" in prompt
    assert "waveguide" in prompt
    assert "silicon" in prompt


def test_build_label_prompt_contains_representative_titles() -> None:
    titles = ["Advances in EUV Lithography", "Silicon Photonic Modulator Design"]
    prompt = build_label_prompt("c_0", [], titles)
    assert "EUV Lithography" in prompt
    assert "Silicon Photonic Modulator Design" in prompt


def test_build_label_prompt_limits_terms_to_15() -> None:
    # Supply 20 terms; only first 15 (term0..term14) should appear
    terms = [f"term{i}" for i in range(20)]
    prompt = build_label_prompt("c_0", terms, [])
    assert "term14" in prompt   # last included
    assert "term15" not in prompt  # first excluded


def test_build_label_prompt_limits_titles_to_n_representative() -> None:
    titles = [f"Title number {i}" for i in range(10)]
    prompt = build_label_prompt("c_0", [], titles)
    assert "Title number 4" in prompt   # 5th title included (0-indexed)
    assert "Title number 5" not in prompt  # 6th title excluded


def test_build_label_prompt_instructs_json_output() -> None:
    prompt = build_label_prompt("c_0", ["photonic"], ["Paper A"])
    assert "JSON" in prompt or "json" in prompt


# ---------------------------------------------------------------------------
# parse_label_response
# ---------------------------------------------------------------------------


def test_parse_label_response_valid_json() -> None:
    text = '{"tagline": "Silicon Photonics", "summary_friendly": "Integrated photonic devices."}'
    tagline, summary = parse_label_response(text, "c_0")
    assert tagline == "Silicon Photonics"
    assert summary == "Integrated photonic devices."


def test_parse_label_response_strips_whitespace() -> None:
    text = '  {"tagline": "EUV Lithography", "summary_friendly": "Extreme UV patterning."} '
    tagline, summary = parse_label_response(text, "c_1")
    assert tagline == "EUV Lithography"
    assert summary == "Extreme UV patterning."


def test_parse_label_response_strips_markdown_fences() -> None:
    text = '```json\n{"tagline": "EUV Lithography", "summary_friendly": "UV patterning."}\n```'
    tagline, summary = parse_label_response(text, "c_0")
    assert tagline == "EUV Lithography"
    assert summary == "UV patterning."


def test_parse_label_response_fallback_on_malformed_json() -> None:
    tagline, summary = parse_label_response("not json at all }{", "c_99")
    assert tagline  # non-empty
    assert summary  # non-empty


def test_parse_label_response_fallback_on_empty_string() -> None:
    tagline, summary = parse_label_response("", "c_7")
    assert tagline
    assert summary


def test_parse_label_response_fallback_on_missing_fields() -> None:
    # JSON parses but neither key is present
    tagline, summary = parse_label_response('{"other_key": "value"}', "c_1")
    assert tagline
    assert summary


def test_parse_label_response_fallback_references_cluster_id() -> None:
    tagline, summary = parse_label_response("", "c_77")
    assert "c_77" in tagline or "c_77" in summary
