# tests/test_tools.py
"""Tests for the LangChain tool implementations (Phase 3)."""

from __future__ import annotations

import pytest

from src.tools.rent_calculator import calculate_deposit_limit
from src.tools.paragraph_lookup import lookup_notice_period
from src.tools.operating_costs import check_rent_brake


# ---------------------------------------------------------------------------
# T1 — calculate_deposit_limit: correct output
# ---------------------------------------------------------------------------
def test_deposit_limit_correct() -> None:
    result = calculate_deposit_limit.invoke({"monthly_net_rent": 850.0})
    assert result["max_deposit_eur"] == 2550.0


# ---------------------------------------------------------------------------
# T2 — calculate_deposit_limit: rejects zero
# ---------------------------------------------------------------------------
def test_deposit_limit_rejects_zero() -> None:
    with pytest.raises(ValueError):
        calculate_deposit_limit.invoke({"monthly_net_rent": 0})


# ---------------------------------------------------------------------------
# T3 — lookup_notice_period: tenant always gets 3 months
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("years", [0, 5, 10])
def test_notice_period_tenant_always_3(years: int) -> None:
    result = lookup_notice_period.invoke(
        {
            "party": "mieter",
            "tenancy_type": "residential",
            "tenancy_years": years,
        }
    )
    assert result["notice_months"] == 3


# ---------------------------------------------------------------------------
# T4 — lookup_notice_period: landlord escalation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "years,expected_months",
    [
        (2, 3),
        (5, 6),
        (8, 9),
    ],
)
def test_notice_period_landlord_escalation(years: int, expected_months: int) -> None:
    result = lookup_notice_period.invoke(
        {
            "party": "vermieter",
            "tenancy_type": "residential",
            "tenancy_years": years,
        }
    )
    assert result["notice_months"] == expected_months


# ---------------------------------------------------------------------------
# T5 — lookup_notice_period: invalid party raises ValueError
# ---------------------------------------------------------------------------
def test_notice_period_invalid_party() -> None:
    with pytest.raises(ValueError):
        lookup_notice_period.invoke(
            {
                "party": "eigentümer",
                "tenancy_type": "residential",
                "tenancy_years": 3,
            }
        )


# ---------------------------------------------------------------------------
# T6 — lookup_notice_period: furnished room uses same-month rule
# ---------------------------------------------------------------------------
def test_notice_period_furnished_room_same_month() -> None:
    result = lookup_notice_period.invoke(
        {"party": "mieter", "tenancy_type": "furnished_room"}
    )
    assert result["notice_months"] == 0
    assert "15." in result["deadline_note"]


# ---------------------------------------------------------------------------
# T7 — lookup_notice_period: temporary residential requires contract text
# ---------------------------------------------------------------------------
def test_notice_period_temporary_requires_contract_text() -> None:
    with pytest.raises(ValueError):
        lookup_notice_period.invoke(
            {"party": "mieter", "tenancy_type": "temporary_residential"}
        )


# ---------------------------------------------------------------------------
# T8 — lookup_notice_period: temporary residential uses contract text
# ---------------------------------------------------------------------------
def test_notice_period_temporary_uses_contract_text() -> None:
    result = lookup_notice_period.invoke(
        {
            "party": "mieter",
            "tenancy_type": "temporary_residential",
            "contractual_notice_description": "14 Tage zum Monatsende",
        }
    )
    assert result["notice_description"] == "14 Tage zum Monatsende"
    assert result["legal_basis"] == "§573c Abs. 2 BGB"


# ---------------------------------------------------------------------------
# T9 — lookup_notice_period: land with monthly rent uses §580a Abs. 1 Nr. 3
# ---------------------------------------------------------------------------
def test_notice_period_land_monthly() -> None:
    result = lookup_notice_period.invoke(
        {
            "party": "vermieter",
            "tenancy_type": "land",
            "payment_interval": "months_or_longer",
        }
    )
    assert result["notice_months"] == 3
    assert result["legal_basis"] == "§580a Abs. 1 Nr. 3 BGB"


# ---------------------------------------------------------------------------
# T10 — lookup_notice_period: other nonbusiness room needs payment interval
# ---------------------------------------------------------------------------
def test_notice_period_nonbusiness_room_requires_payment_interval() -> None:
    with pytest.raises(ValueError):
        lookup_notice_period.invoke(
            {"party": "mieter", "tenancy_type": "other_room_nonbusiness"}
        )


# ---------------------------------------------------------------------------
# T11 — lookup_notice_period: commercial undeveloped land has quarter-end note
# ---------------------------------------------------------------------------
def test_notice_period_commercial_undeveloped_land_special_note() -> None:
    result = lookup_notice_period.invoke(
        {
            "party": "vermieter",
            "tenancy_type": "commercial_undeveloped_land",
            "payment_interval": "months_or_longer",
        }
    )
    assert result["notice_months"] is None
    assert "Kalendervierteljahres" in result["deadline_note"]


# ---------------------------------------------------------------------------
# T12 — lookup_notice_period: commercial space is quarterly
# ---------------------------------------------------------------------------
def test_notice_period_commercial_space_quarterly() -> None:
    result = lookup_notice_period.invoke(
        {"party": "mieter", "tenancy_type": "commercial_space"}
    )
    assert result["notice_quarters"] == 1
    assert result["notice_months"] is None


# ---------------------------------------------------------------------------
# T13 — lookup_notice_period: welfare housing mirrors residential escalation
# ---------------------------------------------------------------------------
def test_notice_period_welfare_landlord_escalation() -> None:
    result = lookup_notice_period.invoke(
        {
            "party": "vermieter",
            "tenancy_type": "welfare_housing",
            "tenancy_years": 8,
        }
    )
    assert result["notice_months"] == 9
    assert "§578 Abs. 3 Satz 1" in result["legal_basis"]


# ---------------------------------------------------------------------------
# T14 — lookup_notice_period: invalid tenancy_type raises ValueError
# ---------------------------------------------------------------------------
def test_notice_period_invalid_tenancy_type() -> None:
    with pytest.raises(ValueError):
        lookup_notice_period.invoke(
            {"party": "mieter", "tenancy_type": "ferienwohnung"}
        )


# ---------------------------------------------------------------------------
# T15 — check_rent_brake: violation detected
# local_comparable_rent=12.5 EUR/qm × 80 qm = 1000 EUR/month; max = 1100
# ---------------------------------------------------------------------------
def test_rent_brake_violation() -> None:
    result = check_rent_brake.invoke(
        {"current_rent": 1200.0, "local_comparable_rent": 12.5, "floor_area_sqm": 80.0}
    )
    assert result["compliant"] is False
    assert result["excess_eur"] == 100.0


# ---------------------------------------------------------------------------
# T16 — check_rent_brake: compliant rent
# local_comparable_rent=12.5 EUR/qm × 80 qm = 1000 EUR/month; max = 1100
# ---------------------------------------------------------------------------
def test_rent_brake_compliant() -> None:
    result = check_rent_brake.invoke(
        {"current_rent": 1050.0, "local_comparable_rent": 12.5, "floor_area_sqm": 80.0}
    )
    assert result["compliant"] is True
    assert result["excess_eur"] == 0.0


# ---------------------------------------------------------------------------
# T17 — check_rent_brake: exempt due to new build
# ---------------------------------------------------------------------------
def test_rent_brake_exempt_new_build() -> None:
    result = check_rent_brake.invoke(
        {
            "current_rent": 1500.0,
            "local_comparable_rent": 12.5,
            "floor_area_sqm": 80.0,
            "built_after_oct_2014": True,
        }
    )
    assert result["exempt"] is True
    assert result["compliant"] is True
    assert result["excess_eur"] == 0.0


# ---------------------------------------------------------------------------
# T18 — check_rent_brake: rejects zero rent
# ---------------------------------------------------------------------------
def test_rent_brake_rejects_zero_rent() -> None:
    with pytest.raises(ValueError):
        check_rent_brake.invoke(
            {"current_rent": 0, "local_comparable_rent": 12.5, "floor_area_sqm": 80.0}
        )
