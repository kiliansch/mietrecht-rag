# src/tools/__init__.py
from src.tools.case_tools import create_deadline, save_draft
from src.tools.operating_costs import check_rent_brake
from src.tools.paragraph_lookup import lookup_notice_period
from src.tools.rent_calculator import calculate_deposit_limit
from src.tools.retrieval_tools import search_law

ALL_TOOLS = [
    calculate_deposit_limit,
    lookup_notice_period,
    check_rent_brake,
    search_law,
    create_deadline,
    save_draft,
]

# Tools that interrupt for user confirmation before executing (HITL). The single
# source of truth for "which actions need approval" — prompt text and UI copy key
# off the interrupt payload's `action`, which matches these names.
APPROVAL_TOOLS = frozenset({"create_deadline", "save_draft"})
