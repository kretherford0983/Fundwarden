# What's new in 1.9 — quick guide

*1.9.0: one person can run a local install with a single account; scheduled automatic backups.*

## 1.9.0: one account on a local install
On a **local install** (PennyWarden on your own Windows, Mac or Linux computer) the person who sets it up gets every
role: Administrator, Budget Manager, Budget Admin, Register User, Register Admin and Auditor. One account can manage
users, keep the budgets and the register, and read the audit log — no second account just to switch hats.

- **Users → New user / Edit:** on a local install all roles are listed together under *Administration*,
  *Financial* and *Audit*; tick any combination. *Budget Admin* still needs *Budget Manager*, and *Register Admin*
  needs *Register User*.
- **Already using PennyWarden locally?** Your account keeps its roles. Open **Users**, edit your own account and
  tick the roles you want. At least one active Administrator must remain.
- **On a server** nothing changes: each user has roles of one security domain, and Administrators cannot change
  their own roles.
