# src/tools/paragraph_lookup.py
"""Tool zur Ermittlung ordentlicher Kündigungsfristen nach §§573c, 578, 580a BGB."""

from __future__ import annotations

from langchain_core.tools import tool

_MONTHLY_DEADLINE_NOTE = (
    "Die Kündigung muss spätestens am dritten Werktag eines Kalendermonats "
    "zugehen, um zum Ablauf des übernächsten Monats wirksam zu sein."
)
_FURNISHED_ROOM_DEADLINE_NOTE = (
    "Die Kündigung muss spätestens am 15. eines Monats zugehen, um zum Ablauf "
    "desselben Monats wirksam zu sein."
)
_WEEKLY_DEADLINE_NOTE = (
    "Die Kündigung muss spätestens am ersten Werktag einer Woche zugehen, um "
    "zum Ablauf des folgenden Sonnabends wirksam zu sein."
)
_DAILY_DEADLINE_NOTE = (
    "Die Kündigung ist an jedem Tag zum Ablauf des folgenden Tages zulässig."
)
_COMMERCIAL_SPACE_DEADLINE_NOTE = (
    "Die Kündigung muss spätestens am dritten Werktag eines Kalendervierteljahres "
    "zugehen, um zum Ablauf des nächsten Kalendervierteljahres wirksam zu sein."
)
_COMMERCIAL_UNDEVELOPED_LAND_DEADLINE_NOTE = (
    "Die Kündigung muss spätestens am dritten Werktag eines Kalendermonats zugehen; "
    "bei gewerblich genutzten unbebauten Grundstücken ist sie bei monatlicher oder "
    "längerer Mietbemessung aber nur zum Ablauf eines Kalendervierteljahres wirksam."
)
_TENANT_PROTECTION_WARNING = (
    "Eine Vereinbarung, die den Mieter gegenüber §573c Abs. 1 oder Abs. 3 BGB "
    "benachteiligt, ist unwirksam (§573c Abs. 4 BGB)."
)

_VALID_PARTIES = {"mieter", "vermieter"}
_VALID_TENANCY_TYPES = {
    "residential",
    "furnished_room",
    "temporary_residential",
    "welfare_housing",
    "land",
    "commercial_undeveloped_land",
    "other_room_nonbusiness",
    "commercial_space",
}

_PARTY_ALIASES = {
    "tenant": "mieter",
    "mieter": "mieter",
    "landlord": "vermieter",
    "vermieter": "vermieter",
}

_TENANCY_TYPE_ALIASES = {
    "wohnraum": "residential",
    "residential": "residential",
    "möbliertes_zimmer": "furnished_room",
    "moebliertes_zimmer": "furnished_room",
    "furnished_room": "furnished_room",
    "vorübergehender_gebrauch": "temporary_residential",
    "voruebergehender_gebrauch": "temporary_residential",
    "temporary_residential": "temporary_residential",
    "wohlfahrtswohnen": "welfare_housing",
    "welfare_housing": "welfare_housing",
    "grundstück": "land",
    "grundstueck": "land",
    "land": "land",
    "gewerblich_genutztes_unbebautes_grundstück": "commercial_undeveloped_land",
    "gewerblich_genutztes_unbebautes_grundstueck": "commercial_undeveloped_land",
    "commercial_undeveloped_land": "commercial_undeveloped_land",
    "sonstige_räume": "other_room_nonbusiness",
    "sonstige_raeume": "other_room_nonbusiness",
    "other_room_nonbusiness": "other_room_nonbusiness",
    "geschäftsraum": "commercial_space",
    "geschaeftsraum": "commercial_space",
    "gewerberaum": "commercial_space",
    "commercial_space": "commercial_space",
}

_PAYMENT_INTERVAL_ALIASES = {
    "tage": "days",
    "daily": "days",
    "day": "days",
    "days": "days",
    "wochen": "weeks",
    "weekly": "weeks",
    "week": "weeks",
    "weeks": "weeks",
    "monatlich": "months_or_longer",
    "monthly": "months_or_longer",
    "months": "months_or_longer",
    "months_or_longer": "months_or_longer",
    "monate_oder_länger": "months_or_longer",
    "monate_oder_laenger": "months_or_longer",
    "längere_zeitabschnitte": "months_or_longer",
    "laengere_zeitabschnitte": "months_or_longer",
}


def _normalise_alias(value: str, aliases: dict[str, str], field_name: str) -> str:
    normalised = value.lower().strip()
    if normalised in aliases:
        return aliases[normalised]
    raise ValueError(
        f"Ungültiger Wert für {field_name}: '{value}'."
    )


def _build_result(
    *,
    party: str,
    tenancy_type: str,
    tenancy_years: int | None,
    payment_interval: str | None,
    contractual_notice_description: str | None,
    notice_months: int | None,
    notice_weeks: int | None,
    notice_days: int | None,
    notice_quarters: int | None,
    notice_description: str,
    legal_basis: str,
    deadline_note: str,
    note: str,
    tenant_protection_warning: str | None = None,
) -> dict:
    return {
        "party": party,
        "tenancy_type": tenancy_type,
        "tenancy_years": tenancy_years,
        "payment_interval": payment_interval,
        "contractual_notice_description": contractual_notice_description,
        "notice_months": notice_months,
        "notice_weeks": notice_weeks,
        "notice_days": notice_days,
        "notice_quarters": notice_quarters,
        "notice_description": notice_description,
        "legal_basis": legal_basis,
        "deadline_note": deadline_note,
        "tenant_protection_warning": tenant_protection_warning,
        "note": note,
    }


def _require_tenancy_years(tenancy_years: int | None) -> int:
    if tenancy_years is None:
        raise ValueError(
            "tenancy_years fehlt. Fragen Sie den Nutzer nach der Anzahl der vollen "
            "Mietjahre seit der Überlassung, bevor Sie dieses Tool aufrufen."
        )
    if tenancy_years < 0:
        raise ValueError("tenancy_years darf nicht negativ sein.")
    return tenancy_years


def _require_payment_interval(payment_interval: str | None) -> str:
    if payment_interval is None or not payment_interval.strip():
        raise ValueError(
            "payment_interval fehlt. Fragen Sie den Nutzer, ob die Miete nach Tagen, "
            "Wochen oder Monaten/längeren Zeitabschnitten bemessen ist, bevor Sie "
            "dieses Tool aufrufen."
        )
    return _normalise_alias(payment_interval, _PAYMENT_INTERVAL_ALIASES, "payment_interval")


def _require_contractual_notice_description(
    contractual_notice_description: str | None,
) -> str:
    if contractual_notice_description is None or not contractual_notice_description.strip():
        raise ValueError(
            "contractual_notice_description fehlt. Bei nur vorübergehend zum Gebrauch "
            "vermietetem Wohnraum kann eine kürzere vertragliche Kündigungsfrist "
            "vereinbart sein. Fragen Sie den Nutzer, ob eine solche Vereinbarung "
            "existiert und wie sie genau lautet, bevor Sie dieses Tool aufrufen."
        )
    return contractual_notice_description.strip()


def _residential_notice_months(party: str, tenancy_years: int) -> int:
    if party == "mieter":
        return 3
    if tenancy_years >= 8:
        return 9
    if tenancy_years >= 5:
        return 6
    return 3


@tool
def lookup_notice_period(
    party: str,
    tenancy_type: str,
    tenancy_years: int | None = None,
    payment_interval: str | None = None,
    contractual_notice_description: str | None = None,
) -> dict:
    """
    Ermittelt die ordentliche Kündigungsfrist nach §§573c, 578 und 580a BGB.

    Verwende dieses Tool immer dann, wenn der Nutzer nach Kündigungsfristen,
    der Frist zur Kündigung eines Mietverhältnisses oder danach fragt,
    wann eine Kündigung wirksam wird.

    Args:
        party: Wer kündigt. Zulässige Werte sind ``mieter`` oder ``vermieter``.
        tenancy_type: Art des Mietverhältnisses. Zulässige Werte sind
            ``residential``, ``furnished_room``, ``temporary_residential``,
            ``welfare_housing``, ``land``, ``commercial_undeveloped_land``,
            ``other_room_nonbusiness`` und ``commercial_space``.
        tenancy_years: Anzahl der vollständigen Mietjahre seit der Überlassung
            (nicht seit Vertragsunterzeichnung). Erforderlich für
            ``residential`` und ``welfare_housing``.
        payment_interval: Für ``land``, ``commercial_undeveloped_land`` und
            ``other_room_nonbusiness`` erforderlich. Zulässige Werte sind
            ``days``, ``weeks`` oder ``months_or_longer``.
        contractual_notice_description: Für ``temporary_residential``
            erforderlich. Hier muss die konkret vereinbarte kürzere
            Kündigungsfrist beschrieben werden.

    Returns:
        Dict mit Mietart, Fristangaben in passenden Einheiten, rechtlicher
        Grundlage und erläuterndem Hinweis.
    """
    normalised_party = _normalise_alias(party, _PARTY_ALIASES, "party")
    if normalised_party not in _VALID_PARTIES:
        raise ValueError(
            f"Ungültige Partei '{party}'. Erlaubte Werte: 'mieter' oder 'vermieter'."
        )

    normalised_tenancy_type = _normalise_alias(
        tenancy_type, _TENANCY_TYPE_ALIASES, "tenancy_type"
    )
    if normalised_tenancy_type not in _VALID_TENANCY_TYPES:
        allowed = ", ".join(sorted(_VALID_TENANCY_TYPES))
        raise ValueError(
            f"Ungültige Mietart '{tenancy_type}'. Erlaubte Werte: {allowed}."
        )

    if tenancy_years is not None and tenancy_years < 0:
        raise ValueError("tenancy_years darf nicht negativ sein.")

    if normalised_tenancy_type in {"residential", "welfare_housing"}:
        years = _require_tenancy_years(tenancy_years)
        notice_months = _residential_notice_months(normalised_party, years)

        if normalised_tenancy_type == "residential":
            if normalised_party == "mieter":
                legal_basis = "§573c Abs. 1 Satz 1 BGB"
            else:
                legal_basis = "§573c Abs. 1 BGB"
            scope_note = ""
        else:
            if normalised_party == "mieter":
                legal_basis = "§578 Abs. 3 Satz 1 i.V.m. §573c Abs. 1 Satz 1 BGB"
            else:
                legal_basis = "§578 Abs. 3 Satz 1 i.V.m. §573c Abs. 1 BGB"
            scope_note = " §573c BGB gilt hier über §578 Abs. 3 Satz 1 BGB entsprechend."

        party_label = "Mieter" if normalised_party == "mieter" else "Vermieter"
        note = (
            f"Bei einer Mietdauer von {years} Jahren seit Überlassung beträgt die "
            f"Kündigungsfrist für den {party_label.lower()} {notice_months} Monate "
            f"gemäß {legal_basis}.{scope_note}"
        )
        return _build_result(
            party=normalised_party,
            tenancy_type=normalised_tenancy_type,
            tenancy_years=years,
            payment_interval=None,
            contractual_notice_description=None,
            notice_months=notice_months,
            notice_weeks=None,
            notice_days=None,
            notice_quarters=None,
            notice_description=f"{notice_months} Monate",
            legal_basis=legal_basis,
            deadline_note=_MONTHLY_DEADLINE_NOTE,
            note=note,
            tenant_protection_warning=_TENANT_PROTECTION_WARNING,
        )

    if normalised_tenancy_type == "furnished_room":
        legal_basis = "§573c Abs. 3 BGB i.V.m. §549 Abs. 2 Nr. 2 BGB"
        note = (
            "Bei möbliertem Wohnraum in der vom Vermieter selbst bewohnten Wohnung "
            "ist die ordentliche Kündigung spätestens am 15. eines Monats zum Ablauf "
            f"desselben Monats zulässig. Die Frist ist für {normalised_party} identisch."
        )
        return _build_result(
            party=normalised_party,
            tenancy_type=normalised_tenancy_type,
            tenancy_years=None,
            payment_interval=None,
            contractual_notice_description=None,
            notice_months=0,
            notice_weeks=None,
            notice_days=None,
            notice_quarters=None,
            notice_description=(
                "Kündigung bis zum 15. eines Monats zum Ablauf desselben Monats"
            ),
            legal_basis=legal_basis,
            deadline_note=_FURNISHED_ROOM_DEADLINE_NOTE,
            note=note,
            tenant_protection_warning=_TENANT_PROTECTION_WARNING,
        )

    if normalised_tenancy_type == "temporary_residential":
        contractual_notice = _require_contractual_notice_description(
            contractual_notice_description
        )
        legal_basis = "§573c Abs. 2 BGB"
        note = (
            "Bei nur vorübergehend zum Gebrauch vermietetem Wohnraum kann eine kürzere "
            "Kündigungsfrist vereinbart werden. Maßgeblich ist die konkret mitgeteilte "
            f"vertragliche Frist: {contractual_notice}."
        )
        return _build_result(
            party=normalised_party,
            tenancy_type=normalised_tenancy_type,
            tenancy_years=None,
            payment_interval=None,
            contractual_notice_description=contractual_notice,
            notice_months=None,
            notice_weeks=None,
            notice_days=None,
            notice_quarters=None,
            notice_description=contractual_notice,
            legal_basis=legal_basis,
            deadline_note="Maßgeblich ist die konkret vereinbarte kürzere Kündigungsfrist.",
            note=note,
        )

    if normalised_tenancy_type == "commercial_space":
        legal_basis = "§580a Abs. 2 BGB"
        note = (
            "Bei Geschäftsräumen ist die ordentliche Kündigung spätestens am dritten "
            "Werktag eines Kalendervierteljahres zum Ablauf des nächsten "
            "Kalendervierteljahres zulässig. Die Frist ist für Mieter und Vermieter "
            "gleich."
        )
        return _build_result(
            party=normalised_party,
            tenancy_type=normalised_tenancy_type,
            tenancy_years=None,
            payment_interval=None,
            contractual_notice_description=None,
            notice_months=None,
            notice_weeks=None,
            notice_days=None,
            notice_quarters=1,
            notice_description=(
                "Kündigung bis zum dritten Werktag eines Kalendervierteljahres zum "
                "Ablauf des nächsten Kalendervierteljahres"
            ),
            legal_basis=legal_basis,
            deadline_note=_COMMERCIAL_SPACE_DEADLINE_NOTE,
            note=note,
        )

    interval = _require_payment_interval(payment_interval)

    if interval == "days":
        return _build_result(
            party=normalised_party,
            tenancy_type=normalised_tenancy_type,
            tenancy_years=None,
            payment_interval=interval,
            contractual_notice_description=None,
            notice_months=None,
            notice_weeks=None,
            notice_days=1,
            notice_quarters=None,
            notice_description="Kündigung an jedem Tag zum Ablauf des folgenden Tages",
            legal_basis="§580a Abs. 1 Nr. 1 BGB",
            deadline_note=_DAILY_DEADLINE_NOTE,
            note=(
                "Bei Mietverhältnissen über Grundstücke oder sonstige Räume, deren "
                "Miete nach Tagen bemessen ist, ist die ordentliche Kündigung an jedem "
                "Tag zum Ablauf des folgenden Tages zulässig. Die Frist ist für Mieter "
                "und Vermieter gleich."
            ),
        )

    if interval == "weeks":
        return _build_result(
            party=normalised_party,
            tenancy_type=normalised_tenancy_type,
            tenancy_years=None,
            payment_interval=interval,
            contractual_notice_description=None,
            notice_months=None,
            notice_weeks=None,
            notice_days=None,
            notice_quarters=None,
            notice_description=(
                "Kündigung spätestens am ersten Werktag einer Woche zum Ablauf des "
                "folgenden Sonnabends"
            ),
            legal_basis="§580a Abs. 1 Nr. 2 BGB",
            deadline_note=_WEEKLY_DEADLINE_NOTE,
            note=(
                "Bei Mietverhältnissen über Grundstücke oder sonstige Räume, deren "
                "Miete nach Wochen bemessen ist, ist die ordentliche Kündigung "
                "spätestens am ersten Werktag einer Woche zum Ablauf des folgenden "
                "Sonnabends zulässig. Die Frist ist für Mieter und Vermieter gleich."
            ),
        )

    if normalised_tenancy_type == "commercial_undeveloped_land":
        return _build_result(
            party=normalised_party,
            tenancy_type=normalised_tenancy_type,
            tenancy_years=None,
            payment_interval=interval,
            contractual_notice_description=None,
            notice_months=None,
            notice_weeks=None,
            notice_days=None,
            notice_quarters=None,
            notice_description=(
                "Kündigung spätestens am dritten Werktag eines Kalendermonats; wirksam "
                "bei monatlicher oder längerer Mietbemessung nur zum Ablauf eines "
                "Kalendervierteljahres"
            ),
            legal_basis="§580a Abs. 1 Nr. 3 BGB",
            deadline_note=_COMMERCIAL_UNDEVELOPED_LAND_DEADLINE_NOTE,
            note=(
                "Bei gewerblich genutzten unbebauten Grundstücken mit monatlicher oder "
                "längerer Mietbemessung ist die Kündigung spätestens am dritten "
                "Werktag eines Kalendermonats zulässig, wirkt aber nur zum Ablauf eines "
                "Kalendervierteljahres. Die Frist ist für Mieter und Vermieter gleich."
            ),
        )

    return _build_result(
        party=normalised_party,
        tenancy_type=normalised_tenancy_type,
        tenancy_years=None,
        payment_interval=interval,
        contractual_notice_description=None,
        notice_months=3,
        notice_weeks=None,
        notice_days=None,
        notice_quarters=None,
        notice_description="3 Monate",
        legal_basis="§580a Abs. 1 Nr. 3 BGB",
        deadline_note=_MONTHLY_DEADLINE_NOTE,
        note=(
            "Bei Mietverhältnissen über Grundstücke oder sonstige Räume, deren Miete "
            "monatlich oder für längere Zeitabschnitte bemessen ist, ist die "
            "ordentliche Kündigung spätestens am dritten Werktag eines "
            "Kalendermonats zum Ablauf des übernächsten Monats zulässig. Die Frist "
            "ist für Mieter und Vermieter gleich."
        ),
    )
