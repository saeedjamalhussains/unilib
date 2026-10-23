# RBAC permission matrix

| Capability | Permission | Administrator | Librarian | Faculty | Student |
|---|---|---:|---:|---:|---:|
| Search catalog and view availability | `catalog.view_book` | Y | Y | Y | Y |
| Add and edit books, authors, publishers, categories | `catalog.manage_catalog` | Y | Y | N | N |
| Delete books | `catalog.delete_book` | Y | N | N | N |
| Manage physical copies | `inventory.manage_copies` | Y | Y | N | N |
| Register and edit members | `membership.manage_members` | Y | Y | N | N |
| View any member profile | `membership.view_all_members` | Y | Y | N | N |
| Create and manage accounts | `accounts.manage_users` | Y | N | N | N |
| Assign roles | `accounts.assign_roles` | Y | N | N | N |
| Edit library policies | `membership.manage_policy` | Y | N | N | N |
| Issue, return and renew for members | `circulation.process_circulation` | Y | Y | N | N |
| View all loans | `circulation.view_all_loans` | Y | Y | N | N |
| View own loans | `circulation.view_own_loans` | N | N | Y | Y |
| Renew own loan | `circulation.renew_own_loan` | N | N | Y | Y |
| Place and cancel own reservation | `reservations.place_reservation` | N | N | Y | Y |
| View and manage all reservations | `reservations.manage_reservations` | Y | Y | N | N |
| View own fines | `fines.view_own_fines` | N | N | Y | Y |
| Record payments and view all fines | `fines.manage_fines` | Y | Y | N | N |
| Waive or adjust fines | `fines.waive_fine` | Y | N | N | N |
| View reports and export CSV | `reports.view_reports` | Y | Y | N | N |
| View audit log | `audit.view_auditlog` | Y | N | N | N |
