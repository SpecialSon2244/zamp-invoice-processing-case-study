from ap_agent.taxids import make_gstin, validate_eu_vat, validate_gstin


def test_known_public_gstin_example_passes_checksum():
    assert validate_gstin("27AAPFU0939F1ZV") == []


def test_gstin_typo_fails_checksum():
    good = make_gstin("33", "AAJFC6612R")
    bad = good[:14] + ("A" if good[14] != "A" else "B")
    assert any("checksum" in p for p in validate_gstin(bad))


def test_gstin_bad_format_and_state():
    assert validate_gstin("29ABC") and "format" in validate_gstin("29ABC")[0]
    assert any("state code" in p for p in validate_gstin(make_gstin("98", "AAFCS7731K")))


def test_eu_vat_formats():
    assert validate_eu_vat("DE274915538") == []
    assert validate_eu_vat("NL853112907B01") == []
    assert validate_eu_vat("DE12345") != []
