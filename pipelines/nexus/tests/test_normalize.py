"""Tests for nexus.assets.entity_resolution.normalize."""

from __future__ import annotations

import pytest

from nexus.assets.entity_resolution.normalize import normalize_org_name

# ---------------------------------------------------------------------------
# Empty / whitespace
# ---------------------------------------------------------------------------


def test_empty_string() -> None:
    assert normalize_org_name("") == ""


def test_whitespace_only() -> None:
    assert normalize_org_name("   ") == ""


# ---------------------------------------------------------------------------
# Casing
# ---------------------------------------------------------------------------


def test_lowercases_input() -> None:
    assert normalize_org_name("NVIDIA") == "nvidia"


def test_mixed_case() -> None:
    assert normalize_org_name("Samsung Electronics") == "samsung electronics"


# ---------------------------------------------------------------------------
# Legal suffix stripping — single suffix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("NVIDIA Corporation", "nvidia"),
        ("NVIDIA Corp", "nvidia"),
        ("NVIDIA Inc", "nvidia"),
        ("NVIDIA Incorporated", "nvidia"),
        ("Tokyo Electron Ltd", "tokyo electron"),
        ("Tokyo Electron Limited", "tokyo electron"),
        ("Arm Holdings", "arm"),
        ("Arm Holdings Group", "arm"),  # two suffixes stripped
        ("Samsung Group", "samsung"),
    ],
)
def test_single_suffix_stripped(raw: str, expected: str) -> None:
    assert normalize_org_name(raw) == expected


# ---------------------------------------------------------------------------
# Legal suffix stripping — multiple suffixes (stacked)
# ---------------------------------------------------------------------------


def test_stacked_suffixes_samsung() -> None:
    # "Samsung Electronics Co., Ltd." → "samsung electronics"
    assert normalize_org_name("Samsung Electronics Co., Ltd.") == "samsung electronics"


def test_stacked_suffixes_tok() -> None:
    # "Tokyo Electron Ltd. Co." → strip co → strip ltd → "tokyo electron"
    assert normalize_org_name("Tokyo Electron Ltd. Co.") == "tokyo electron"


# ---------------------------------------------------------------------------
# Dotted abbreviations — European / international legal forms
# ---------------------------------------------------------------------------


def test_nv_dotted() -> None:
    # "ASML Holding N.V." → "asml"  (holding stripped, nv expanded then stripped)
    assert normalize_org_name("ASML Holding N.V.") == "asml"


def test_bv() -> None:
    assert normalize_org_name("Philips Research B.V.") == "philips research"


def test_plc() -> None:
    assert normalize_org_name("ARM Holdings P.L.C.") == "arm"


def test_llc() -> None:
    assert normalize_org_name("Applied Micro Circuits L.L.C.") == "applied micro circuits"


def test_ltd_dotted() -> None:
    assert normalize_org_name("Tokyo Electron L.T.D.") == "tokyo electron"


def test_gmbh() -> None:
    assert normalize_org_name("Zeiss G.M.B.H.") == "zeiss"


def test_ag() -> None:
    assert normalize_org_name("Infineon Technologies A.G.") == "infineon technologies"


def test_sa_dotted() -> None:
    assert normalize_org_name("STMicroelectronics S.A.") == "stmicroelectronics"


def test_sas() -> None:
    assert normalize_org_name("Soitec S.A.S.") == "soitec"


def test_srl() -> None:
    # Italian S.r.l. (e.g. STMicroelectronics S.r.l.)
    assert normalize_org_name("STMICROELECTRONICS S.r.l.") == "stmicroelectronics"


def test_kabushiki_kaisha_suffix() -> None:
    # "KABUSHIKI KAISHA" at the end — both stripped right-to-left
    assert normalize_org_name("CANON KABUSHIKI KAISHA") == "canon"


def test_kabushiki_kaisha_prefix_not_stripped() -> None:
    # "Kabushiki Kaisha" at the START — suffix stripping is right-anchored; "toshiba"
    # is not itself a suffix, so stripping stops before reaching kabushiki/kaisha.
    assert normalize_org_name("Kabushiki Kaisha Toshiba") == "kabushiki kaisha toshiba"


def test_kk() -> None:
    # Kabushiki Kaisha (Japanese company form)
    assert normalize_org_name("Shin-Etsu Chemical Co. KK") == "shin etsu chemical"


# ---------------------------------------------------------------------------
# Unicode → ASCII
# ---------------------------------------------------------------------------


def test_accented_chars_stripped() -> None:
    # é → e
    assert normalize_org_name("Société Générale") == "societe generale"


def test_german_umlaut() -> None:
    # ü → u
    assert normalize_org_name("Müller GmbH") == "muller"


# ---------------------------------------------------------------------------
# Punctuation removal
# ---------------------------------------------------------------------------


def test_punctuation_replaced_by_space() -> None:
    # Hyphens, commas, dots become spaces then collapse
    result = normalize_org_name("Shin-Etsu Chemical")
    assert result == "shin etsu chemical"


def test_ampersand_removed() -> None:
    result = normalize_org_name("Research & Development Corp")
    assert result == "research development"


def test_parentheses_removed() -> None:
    result = normalize_org_name("IBM (International Business Machines) Corp")
    assert result == "ibm international business machines"


# ---------------------------------------------------------------------------
# Key scope players — end-to-end spot checks
# (these are the orgs that will appear in both data sources)
# ---------------------------------------------------------------------------


def test_nvidia_variants_all_same() -> None:
    v1 = normalize_org_name("NVIDIA")
    v2 = normalize_org_name("NVIDIA Corp")
    v3 = normalize_org_name("Nvidia Corporation")
    assert v1 == v2 == v3 == "nvidia"


def test_stanford_university_preserved() -> None:
    # "university" is not a legal suffix — must be kept
    assert normalize_org_name("Stanford University") == "stanford university"


def test_mit_preserved() -> None:
    expected = "massachusetts institute of technology"
    assert normalize_org_name("Massachusetts Institute of Technology") == expected


def test_tsmc() -> None:
    v1 = normalize_org_name("Taiwan Semiconductor Manufacturing Company")
    v2 = normalize_org_name("Taiwan Semiconductor Manufacturing Co., Ltd.")
    assert v1 == v2 == "taiwan semiconductor manufacturing"


def test_asml() -> None:
    v1 = normalize_org_name("ASML")
    v2 = normalize_org_name("ASML Holding N.V.")
    assert v1 == v2 == "asml"


def test_imec() -> None:
    assert normalize_org_name("IMEC vzw") == "imec vzw"  # vzw not in suffix list — kept


def test_intel() -> None:
    v1 = normalize_org_name("Intel Corporation")
    v2 = normalize_org_name("Intel Corp")
    assert v1 == v2 == "intel"


def test_ibm() -> None:
    assert normalize_org_name("International Business Machines Corp") == (
        "international business machines"
    )


def test_sk_hynix() -> None:
    v1 = normalize_org_name("SK Hynix Inc")
    v2 = normalize_org_name("SK Hynix")
    assert v1 == v2 == "sk hynix"


# ---------------------------------------------------------------------------
# Edge cases — name is itself a suffix word (must not produce empty string)
# ---------------------------------------------------------------------------


def test_name_that_is_only_suffix_kept() -> None:
    # Single-token name that happens to be a suffix word — must not be stripped
    assert normalize_org_name("Corp") == "corp"


def test_two_token_name_one_is_suffix() -> None:
    # Last token stripped, first kept
    assert normalize_org_name("Acme Corp") == "acme"
