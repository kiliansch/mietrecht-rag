# src/tools/rent_calculator.py
"""Tool zur Berechnung der gesetzlich zulässigen Mietkaution gemäß §551 BGB."""

from __future__ import annotations

from langchain_core.tools import tool


@tool
def calculate_deposit_limit(monthly_net_rent: float) -> dict:
    """
    Berechnet die gesetzlich zulässige Höchstkaution gemäß §551 BGB.

    Verwende dieses Tool immer dann, wenn der Nutzer nach der maximalen Kaution,
    Mietsicherheit oder dem zulässigen Kautionsbetrag fragt.
    Eingabe: monatliche Nettokaltmiete (Grundmiete) in EUR.
    Ausgabe: maximale Kaution in EUR (3 Monatsnettokaltmieten).
    """
    if monthly_net_rent <= 0:
        raise ValueError("monthly_net_rent muss größer als 0 EUR sein.")
    max_deposit_eur = round(monthly_net_rent * 3, 2)
    return {
        "max_deposit_eur": max_deposit_eur,
        "monthly_net_rent": monthly_net_rent,
        "multiplier": 3,
        "legal_basis": "§551 Abs. 1 BGB",
        "note": (
            f"Bei einer Nettokaltmiete von {monthly_net_rent:.2f} EUR darf die Kaution "
            f"gemäß §551 BGB maximal {max_deposit_eur:.2f} EUR betragen "
            f"(3 Monatsnettokaltmieten)."
        ),
    }
