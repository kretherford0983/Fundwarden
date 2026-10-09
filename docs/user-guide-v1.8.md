# What's new in 1.8 — quick guide

*1.8.0: budgets linked across Fiscal Years, the Financial Flow Report, a forgotten password reset with security
questions, and configuration notes for the Mac.*

## 1.8.0: budgets across Fiscal Years
A budget's ID or name sometimes changes from one year to the next. To keep track, open the budget's **Edit** dialog
(or create the budget) and choose in **Continues** the budget of an earlier year it carries on, e.g.
`FY2027 - 1000 - Operations`. The list offers budgets of the same type and level that no other budget continues yet.

- Budgets you **copy** into a new Fiscal Year are linked to their source for you.
- A budget with a link shows **History** next to its name on the Budgets page: every year of that budget with its
  ID, name, amount and actual, oldest first; the one you opened it from is highlighted.
- Choose **— None —** to remove a link. A locked budget is unlocked first, as for any other change.

## 1.8.0: configuration on a Mac
docs/configuration.md now has a section for the Mac: where the data folder and the log are
(`~/Library/Application Support/PennyWarden`, hidden in Finder — use **Go → Go to Folder…**), how to change settings
with `config.toml`, and how to start the app with options from Terminal.
