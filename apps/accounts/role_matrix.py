from dataclasses import dataclass

ROLES = ("Administrator", "Librarian", "Faculty", "Student")


@dataclass(frozen=True)
class Capability:
    description: str
    permission: str
    roles: tuple[str, ...]


CAPABILITIES = (
    Capability("Search catalog and view availability", "catalog.view_book", ROLES),
    Capability(
        "Add and edit books, authors, publishers, categories",
        "catalog.manage_catalog",
        ("Administrator", "Librarian"),
    ),
    Capability("Delete books", "catalog.delete_book", ("Administrator",)),
    Capability("Manage physical copies", "inventory.manage_copies", ("Administrator", "Librarian")),
    Capability("Register and edit members", "membership.manage_members", ("Administrator", "Librarian")),
    Capability("View any member profile", "membership.view_all_members", ("Administrator", "Librarian")),
    Capability("Create and manage accounts", "accounts.manage_users", ("Administrator",)),
    Capability("Assign roles", "accounts.assign_roles", ("Administrator",)),
    Capability("Edit library policies", "membership.manage_policy", ("Administrator",)),
    Capability(
        "Issue, return and renew for members",
        "circulation.process_circulation",
        ("Administrator", "Librarian"),
    ),
    Capability("View all loans", "circulation.view_all_loans", ("Administrator", "Librarian")),
    Capability("View own loans", "circulation.view_own_loans", ("Faculty", "Student")),
    Capability("Renew own loan", "circulation.renew_own_loan", ("Faculty", "Student")),
    Capability("Place and cancel own reservation", "reservations.place_reservation", ("Faculty", "Student")),
    Capability("View and manage all reservations", "reservations.manage_reservations", ("Administrator", "Librarian")),
    Capability("View own fines", "fines.view_own_fines", ("Faculty", "Student")),
    Capability("Record payments and view all fines", "fines.manage_fines", ("Administrator", "Librarian")),
    Capability("Waive or adjust fines", "fines.waive_fine", ("Administrator",)),
    Capability("View reports and export CSV", "reports.view_reports", ("Administrator", "Librarian")),
    Capability("View audit log", "audit.view_auditlog", ("Administrator",)),
)


def matrix_markdown():
    lines = [
        "# RBAC permission matrix",
        "",
        "| Capability | Permission | Administrator | Librarian | Faculty | Student |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for capability in CAPABILITIES:
        allowed = ["Y" if role in capability.roles else "N" for role in ROLES]
        lines.append(
            f"| {capability.description} | `{capability.permission}` | "
            + " | ".join(allowed)
            + " |"
        )
    return "\n".join(lines) + "\n"
