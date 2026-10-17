"""What a member of a workspace may do, as a list of named permissions.

A role is a set of these. The three roles the product always had, and the virtual `manager`, are
fixed in code (below), and grant exactly what they always did. A workspace's owner can add roles of
their own, each a subset of the catalog, and give them to members: an accountant who may only
export, a clerk who may enter and import but not configure.

What this covers, deliberately:

- **Writes** are per area (`transactions.write`, `invoices.write`...). Every mutating route asks for
  one (`require_permission`), and `tests/test_write_permission_coverage.py` fails for a route that
  asks for none.
- **Reading the workspace's data** is *not* a permission: anyone who is a member can look at the
  workspace's accounts, transactions and reports, as before. Restricting what a member can *see* is
  a different and larger change (every query, every report) and has not been made.
- **Export** and the **audit trail** are permissions, because they take the data out, or show who did
  what.
- **Administration** (`workspace.manage`, `members.manage`, `roles.manage`) is what an owner had alone.

Adding a permission is adding a line here; nothing else has to know about it until a route asks
for it.
"""
from __future__ import annotations

from dataclasses import dataclass

GROUPS = ("data", "reports", "admin")


@dataclass(frozen=True)
class Permission:
    key: str
    group: str


_CATALOG: tuple[Permission, ...] = (
    # --- data: one per area of the product, for creating, changing and deleting -------------
    Permission("transactions.write", "data"),  # transactions and their attachments
    Permission("accounts.write", "data"),
    Permission("categories.write", "data"),  # categories and category groups
    Permission("rules.write", "data"),
    Permission("planning.write", "data"),  # budgets, goals, recurring transactions
    Permission("payees.write", "data"),
    Permission("assets.write", "data"),  # assets and asset groups
    Permission("imports.write", "data"),  # importing transactions, the import log
    Permission("collections.write", "data"),
    Permission("groups.write", "data"),  # split-expense groups
    Permission("connections.write", "data"),  # bank connections and their sync
    Permission("invoices.write", "data"),
    Permission("reconciliation.write", "data"),
    Permission("agents.manage", "data"),  # AI agents, their knowledge, tokens and chats
    Permission("approvals.approve", "data"),  # approve or reject pending transactions
    # --- reports: taking data out, and seeing who did what ---------------------------------
    Permission("export.read", "reports"),  # backup and the accountant's package
    Permission("audit.read", "reports"),
    # --- admin: what only an owner could do -------------------------------------------------
    Permission("workspace.manage", "admin"),  # settings, modules, archiving
    Permission("members.manage", "admin"),  # invite, change a role, remove
    Permission("roles.manage", "admin"),  # create and edit the workspace's own roles
    Permission("tokens.manage", "admin"),  # make, rotate and revoke API tokens
    Permission("periods.manage", "admin"),   # close and reopen accounting periods
    Permission("webhooks.manage", "admin"),  # create, edit and delete outbound webhook endpoints
    Permission("fiscal.emit", "data"),       # emit NF-e for invoices
    Permission("fiscal.admin", "admin"),     # configure fiscal provider credentials
    Permission("billing.read", "read"),      # view boleto/PIX charges
    Permission("billing.manage", "admin"),   # create charges and configure billing provider
    Permission("erp.read", "reports"),       # see ERP connections, mappings and sync history
    Permission("erp.manage", "admin"),       # connect an ERP, hold its credentials, trigger syncs
    Permission("payments.read", "reports"),   # ver ordens de pagamento
    Permission("payments.write", "data"),     # criar, editar e cancelar ordens
    Permission("payments.approve", "admin"),  # aprovar/rejeitar (a dupla aprovação é sempre exigida)
    Permission("payments.send", "admin"),     # enviar a ordem aprovada ao provedor
)

PERMISSIONS: dict[str, Permission] = {p.key: p for p in _CATALOG}
ALL_PERMISSIONS: frozenset[str] = frozenset(PERMISSIONS)
WRITE_PERMISSIONS: frozenset[str] = frozenset(p.key for p in _CATALOG if p.group == "data")
ADMIN_PERMISSIONS: frozenset[str] = frozenset(p.key for p in _CATALOG if p.group == "admin")

# --- the roles the product always had ----------------------------------------------------------

#: role key -> permissions. `manager` is the virtual role of someone who administers a workspace
#: from outside it; it has always been an owner in effect.
SYSTEM_ROLES: dict[str, frozenset[str]] = {
    "owner": ALL_PERMISSIONS,
    "manager": ALL_PERMISSIONS,
    # Read and write the financial data and export it; no administration, no audit trail.
    "editor": WRITE_PERMISSIONS | {"export.read"},
    # Read-only. (It could always take the data out through the backup and the accountant's
    # package, so it keeps `export.read`; a custom role may leave that out.)
    "viewer": frozenset({"export.read"}),
}

SYSTEM_ROLE_KEYS = ("owner", "editor", "viewer")


def is_system_role(key: str) -> bool:
    return key in SYSTEM_ROLES


# --- ready-made starting points for a workspace's own roles -------------------------------------


@dataclass(frozen=True)
class RoleTemplate:
    key: str
    permissions: frozenset[str]


#: Offered when creating a role; the owner can change anything after picking one.
TEMPLATES: tuple[RoleTemplate, ...] = (
    # Reads everything and takes the data out for the books: nothing that changes data.
    RoleTemplate("accountant", frozenset({"export.read"})),
    # Reads, and sees who did what.
    RoleTemplate("auditor", frozenset({"export.read", "audit.read"})),
    # Enters and reconciles: transactions, accounts, imports and matching invoices to payments;
    # no configuration, no administration.
    RoleTemplate(
        "clerk",
        frozenset(
            {
                "transactions.write",
                "accounts.write",
                "imports.write",
                "payees.write",
                "reconciliation.write",
            }
        ),
    ),
    # Issues and follows up invoices, and takes the reports out.
    RoleTemplate("billing", frozenset({"invoices.write", "payees.write", "export.read"})),
)


def normalise(permissions: list[str] | set[str] | frozenset[str]) -> frozenset[str]:
    """The permissions as a set, or ValueError naming the ones the catalog does not have."""
    unknown = sorted(set(permissions) - ALL_PERMISSIONS)
    if unknown:
        raise ValueError(f"Unknown permissions: {', '.join(unknown)}")
    return frozenset(permissions)
