from src.contracts.extract_facts import extract_tenancy_facts


def test_extract_floor_area_m2_symbol():
    facts = extract_tenancy_facts("Die Wohnung hat eine Größe von 72 m².")
    assert facts == {"floor_area_sqm": 72.0}


def test_extract_floor_area_qm_with_decimal_comma():
    facts = extract_tenancy_facts("Wohnfläche: 72,5 qm")
    assert facts == {"floor_area_sqm": 72.5}


def test_extract_floor_area_quadratmeter_word():
    facts = extract_tenancy_facts("Die Wohnfläche beträgt 72 Quadratmeter.")
    assert facts == {"floor_area_sqm": 72.0}


def test_extract_net_rent_nettokaltmiete_thousands():
    facts = extract_tenancy_facts("Die Nettokaltmiete beträgt 1.200,50 €.")
    assert facts == {"monthly_net_rent": 1200.50}


def test_extract_net_rent_kaltmiete_eur():
    facts = extract_tenancy_facts("Kaltmiete: 850 EUR monatlich.")
    assert facts == {"monthly_net_rent": 850.0}


def test_extract_both_facts_together():
    text = "Wohnfläche 72 m². Nettokaltmiete 850 €."
    facts = extract_tenancy_facts(text)
    assert facts == {"floor_area_sqm": 72.0, "monthly_net_rent": 850.0}


def test_extract_unrelated_text_yields_no_keys():
    facts = extract_tenancy_facts("Dieser Vertrag wird zwischen den Parteien geschlossen.")
    assert facts == {}


def test_extract_bare_numbers_without_unit_yield_no_keys():
    facts = extract_tenancy_facts("Der Vertrag hat die Nummer 72 und Absatz 850.")
    assert facts == {}
