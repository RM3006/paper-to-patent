"""Tests for the document_clusters pure helpers."""

from nexus.assets.ml.clustering import (
    compute_ctfidf_terms,
    corpus_signature,
    make_cluster_id,
)

# ---------------------------------------------------------------------------
# make_cluster_id
# ---------------------------------------------------------------------------


def test_make_cluster_id_noise() -> None:
    assert make_cluster_id(-1) == "c_noise"


def test_make_cluster_id_zero() -> None:
    assert make_cluster_id(0) == "c_0"


def test_make_cluster_id_positive() -> None:
    assert make_cluster_id(42) == "c_42"


# ---------------------------------------------------------------------------
# corpus_signature — the freeze fingerprint
# ---------------------------------------------------------------------------


def test_corpus_signature_is_deterministic() -> None:
    ids = ["W3", "W1", "P2", "W1"]
    assert corpus_signature(ids) == corpus_signature(ids)


def test_corpus_signature_order_independent() -> None:
    # read order must not change the fingerprint (freeze must survive re-sorts)
    assert corpus_signature(["W1", "W2", "P3"]) == corpus_signature(["P3", "W2", "W1"])


def test_corpus_signature_duplicate_independent() -> None:
    # a duplicated id is the same corpus content
    assert corpus_signature(["W1", "W2"]) == corpus_signature(["W1", "W2", "W2"])


def test_corpus_signature_changes_when_a_document_is_added() -> None:
    # onboarding a new document MUST change the signature (triggers a re-cut)
    before = corpus_signature(["W1", "W2"])
    after = corpus_signature(["W1", "W2", "W3"])
    assert before != after


def test_corpus_signature_changes_when_a_document_is_removed() -> None:
    assert corpus_signature(["W1", "W2", "W3"]) != corpus_signature(["W1", "W2"])


def test_corpus_signature_is_16_char_hex() -> None:
    sig = corpus_signature(["W1", "W2", "W3"])
    assert len(sig) == 16
    assert all(c in "0123456789abcdef" for c in sig)


# ---------------------------------------------------------------------------
# compute_ctfidf_terms
# ---------------------------------------------------------------------------

# Two clusters with strongly distinct vocabulary so c-TF-IDF reliably
# surfaces the right terms even at small doc counts.
_CLUSTER_0 = [
    "photonic waveguide silicon optical ring resonator",
    "silicon photonic modulator waveguide optical coupling",
    "optical waveguide photonic silicon chip fabrication",
    "photonic crystal silicon waveguide optical mode",
    "silicon photonic integrated circuit waveguide optical",
]
_CLUSTER_1 = [
    "memristor synaptic neural weight learning rule",
    "neural network memristive synaptic weight update",
    "synaptic memristor neural weight training gradient",
    "memristive neural synaptic weight plasticity rule",
    "neural memristor synaptic weight crossbar array",
]

_DOC_IDS = [f"d{i}" for i in range(10)]
_LABELS = [0, 0, 0, 0, 0, 1, 1, 1, 1, 1]
_ID_TO_TEXT = dict(zip(_DOC_IDS, _CLUSTER_0 + _CLUSTER_1, strict=True))


def test_compute_ctfidf_returns_all_cluster_keys() -> None:
    result = compute_ctfidf_terms(_DOC_IDS, _LABELS, _ID_TO_TEXT, n_terms=5)
    assert "c_0" in result
    assert "c_1" in result
    assert "c_noise" in result


def test_compute_ctfidf_noise_gets_empty_list() -> None:
    result = compute_ctfidf_terms(_DOC_IDS, _LABELS, _ID_TO_TEXT, n_terms=5)
    assert result["c_noise"] == []


def test_compute_ctfidf_top_terms_respect_n_terms() -> None:
    result = compute_ctfidf_terms(_DOC_IDS, _LABELS, _ID_TO_TEXT, n_terms=5)
    assert len(result["c_0"]) == 5
    assert len(result["c_1"]) == 5


def test_compute_ctfidf_cluster0_terms_are_photonic_domain() -> None:
    result = compute_ctfidf_terms(_DOC_IDS, _LABELS, _ID_TO_TEXT, n_terms=10)
    photonic_terms = {"photonic", "waveguide", "silicon", "optical"}
    # At least 3 of the top-10 terms should be from the photonic domain
    c0_set = set(result["c_0"])
    matches = photonic_terms & c0_set
    assert len(matches) >= 3, f"Expected photonic terms in c_0 top-10, got: {result['c_0']}"


def test_compute_ctfidf_cluster1_terms_are_neural_domain() -> None:
    result = compute_ctfidf_terms(_DOC_IDS, _LABELS, _ID_TO_TEXT, n_terms=10)
    neural_terms = {"memristor", "synaptic", "neural", "weight"}
    c1_set = set(result["c_1"])
    matches = neural_terms & c1_set
    assert len(matches) >= 3, f"Expected neural terms in c_1 top-10, got: {result['c_1']}"


def test_compute_ctfidf_all_noise_returns_empty() -> None:
    doc_ids = ["d0", "d1"]
    labels = [-1, -1]
    id_to_text = {"d0": "some text here", "d1": "other text here"}
    result = compute_ctfidf_terms(doc_ids, labels, id_to_text)
    assert result == {"c_noise": []}


def test_compute_ctfidf_missing_text_handled_gracefully() -> None:
    # doc d2 is not in id_to_text → should be skipped without error
    doc_ids = ["d0", "d1", "d2"]
    labels = [0, 0, 0]
    id_to_text = {
        "d0": "photonic waveguide silicon optical",
        "d1": "silicon photonic waveguide optical chip",
        # d2 missing
    }
    result = compute_ctfidf_terms(doc_ids, labels, id_to_text, n_terms=3)
    assert "c_0" in result
    assert len(result["c_0"]) <= 3


def test_compute_ctfidf_with_noise_docs_mixed_in() -> None:
    # Noise docs (label=-1) should not pollute cluster term extraction
    doc_ids = _DOC_IDS + ["noise0", "noise1"]
    labels = _LABELS + [-1, -1]
    id_to_text = dict(_ID_TO_TEXT)
    id_to_text["noise0"] = "completely unrelated random garbage words"
    id_to_text["noise1"] = "another unrelated noise document totally different"
    result = compute_ctfidf_terms(doc_ids, labels, id_to_text, n_terms=5)
    # Cluster quality should be unaffected
    photonic_terms = {"photonic", "waveguide", "silicon", "optical"}
    assert len(photonic_terms & set(result["c_0"])) >= 2
    assert result["c_noise"] == []
