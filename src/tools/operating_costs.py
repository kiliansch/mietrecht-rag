# src/tools/operating_costs.py
"""Tool zur Prüfung der Mietpreisbremse gemäß §556d BGB."""

from __future__ import annotations

from langchain_core.tools import tool

_GRANDFATHERING_WARNING = (
    "Hinweis: Falls die Vormiete bereits über der Mietpreisbremse lag, "
    "kann dieser höhere Betrag unter Umständen beibehalten werden "
    "(§556e BGB). Bitte prüfen Sie die Vormiete separat."
)


@tool
def check_rent_brake(
    current_rent: float,
    local_comparable_rent: float,
    floor_area_sqm: float,
    built_after_oct_2014: bool = False,
    comprehensively_modernised: bool = False,
) -> dict:
    """
    Prüft, ob eine Miete die Mietpreisbremse gemäß §556d BGB einhält.

    Verwende dieses Tool immer dann, wenn der Nutzer fragt, ob eine Miete
    zu hoch ist, ob die Mietpreisbremse gilt, oder welche Miete zulässig ist.

    Args:
        current_rent: Die verlangte Nettokaltmiete (Kaltmiete ohne Nebenkosten)
            in EUR/Monat.
        local_comparable_rent: Die ortsübliche Vergleichsmiete aus dem Mietspiegel
            in EUR pro Quadratmeter (EUR/qm). Wird intern mit floor_area_sqm
            multipliziert, um die monatliche Vergleichsmiete zu erhalten.
        floor_area_sqm: Wohnfläche in Quadratmetern (zwingend erforderlich).
        built_after_oct_2014: True, wenn die Wohnung nach dem 1. Oktober 2014
            erstmals genutzt und vermietet wurde (Ausnahme §556f BGB).
        comprehensively_modernised: True, wenn die Wohnung in den letzten 3 Jahren
            vor Mietbeginn umfassend modernisiert wurde (Ausnahme §556f BGB).

    Returns:
        Dict mit Prüfergebnis, zulässiger Höchstmiete, Überschreitungsbetrag und
        rechtlicher Grundlage.
    """
    if current_rent <= 0 or local_comparable_rent <= 0:
        raise ValueError("Mieten müssen größer als 0 EUR sein.")
    if floor_area_sqm <= 0:
        raise ValueError(
            "Wohnfläche (floor_area_sqm) fehlt oder ist 0. "
            "Bitte fragen Sie den Nutzer nach der Wohnfläche in Quadratmetern, "
            "bevor Sie dieses Tool aufrufen."
        )

    # Always compute monthly comparable rent from per-sqm Mietspiegel value
    comparable_rent_monthly = round(local_comparable_rent * floor_area_sqm, 2)

    if built_after_oct_2014:
        exempt = True
        exemption_reason = (
            "Die Wohnung wurde nach dem 1. Oktober 2014 erstmals genutzt "
            "und vermietet. Die Mietpreisbremse gilt nicht (§556f BGB)."
        )
    elif comprehensively_modernised:
        exempt = True
        exemption_reason = (
            "Die Wohnung wurde in den letzten 3 Jahren vor Mietbeginn "
            "umfassend modernisiert. Die Mietpreisbremse gilt nicht (§556f BGB)."
        )
    else:
        exempt = False
        exemption_reason = ""

    if exempt:
        max_permitted_rent = -1.0
        compliant = True
        excess_eur = 0.0
        note = (
            f"Die Mietpreisbremse gilt für diese Wohnung nicht. "
            f"Grund: {exemption_reason}"
        )
    else:
        max_permitted_rent = round(comparable_rent_monthly * 1.10, 2)
        compliant = current_rent <= max_permitted_rent
        excess_eur = round(max(0.0, current_rent - max_permitted_rent), 2)
        if compliant:
            note = (
                f"Die verlangte Miete von {current_rent:.2f} EUR liegt innerhalb "
                f"der zulässigen Höchstmiete von {max_permitted_rent:.2f} EUR "
                f"(ortsübliche Vergleichsmiete {comparable_rent_monthly:.2f} EUR/Monat"
                f" = {local_comparable_rent:.2f} EUR/qm × {floor_area_sqm} qm + 10 %)."
            )
        else:
            note = (
                f"Die verlangte Miete von {current_rent:.2f} EUR überschreitet "
                f"die zulässige Höchstmiete von {max_permitted_rent:.2f} EUR "
                f"um {excess_eur:.2f} EUR."
            )

    return {
        "exempt": exempt,
        "exemption_reason": exemption_reason,
        "current_rent": current_rent,
        "local_comparable_rent_per_sqm": local_comparable_rent,
        "local_comparable_rent_monthly": comparable_rent_monthly,
        "floor_area_sqm": floor_area_sqm,
        "max_permitted_rent": max_permitted_rent,
        "compliant": compliant,
        "excess_eur": excess_eur,
        "legal_basis": "§556d Abs. 1 BGB",
        "grandfathering_warning": _GRANDFATHERING_WARNING,
        "note": note,
    }
