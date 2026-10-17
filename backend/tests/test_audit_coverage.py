"""A new model has to be a decision: audited, or exempt with a reason.

Without this a table added next month would quietly never reach the audit trail, and the
promise "every financial or configuration change is recorded" would rot one model at a time.
"""
from app.core.audit import AUDITED_TABLES, EXEMPT
from app.core.database import Base


def _tables() -> set[str]:
    return {table.name for table in Base.metadata.sorted_tables}


def test_every_model_is_audited_or_exempt_for_a_stated_reason():
    audited = AUDITED_TABLES
    undecided = _tables() - audited - set(EXEMPT)
    assert undecided == set(), (
        f"decide for {sorted(undecided)}: add to AUDITED in app/core/audit.py, "
        "or to EXEMPT with the reason it does not belong in the trail"
    )


def test_nothing_is_both():
    audited = AUDITED_TABLES
    assert audited & set(EXEMPT) == set()


def test_no_stale_entries():
    assert set(EXEMPT) - _tables() == set(), "EXEMPT names a table that no model has"


def test_every_exemption_has_a_reason():
    assert all(reason.strip() for reason in EXEMPT.values())


def test_every_model_with_a_workspace_that_carries_money_or_config_is_not_exempt():
    """The tables that hold the workspace's own data must be audited, whatever else changes."""
    must_audit = {
        "transactions", "accounts", "categories", "budgets", "invoices", "workspaces",
        "workspace_members", "users", "bank_connections", "rules", "recurring_transactions",
    }
    assert must_audit <= AUDITED_TABLES
