# What's new in 1.7 — quick guide

*1.7.0: the application is renamed PennyWarden. 1.7.1: your name in the top bar, a display name for every user.*

## 1.7.1: your name in the top bar
The top bar now shows your **display name** — for example *Jordan Lee* — instead of your username, and no longer
lists your roles next to it. Your username, email address and roles are on **My account**.

**Administrators:** every user now has a display name of at least 3 characters.
- **New user:** *Display name* must be filled in. Leaving it empty gives "Display name is required."; fewer than 3
  characters gives "Display name must be at least 3 characters." Spaces before and after the name are removed.
- **Editing a user:** the display name can be changed but not removed.
- **Existing users** who had no display name were given their username as display name by the upgrade — nothing
  looks different for them until you enter their real name under **Users → Edit**. The Users list has a
  *Display name* column so you can see who still shows a username.
- The first Administrator created by the Initialization Wizard also starts with the username as display name.

## 1.7.0: a new name — PennyWarden
The application is now called **PennyWarden**. Another product in the financial field already uses the name it had
from 1.6.6 to 1.6.8 (*Fundwarden*). The icon — the gold coin with a keyhole — stays.

**Nothing about your work changes:** same address, same sign-in, same data, same screens.

What you may notice:
- The name in the browser tab, on the sign-in page, in the top bar and on reports.
- **Two-step verification** keeps working. The entry in your authenticator app keeps its old label; you do not need
  to set anything up again. A new set-up is labelled *PennyWarden*.
- **Backups** are now named `pennywarden-backup-…`. Backup files made earlier restore exactly as before.
- **Bookmarks** keep working — the address of your installation has not changed.

## If you look after the installation
- **Server (Linux):** run the usual upgrade command. The installer moves the installation to the new name by
  itself and leaves the old one in place until you remove it. Steps, going back and the cleanup checklist:
  [upgrade.md](upgrade.md), *1.7.0: the rename to PennyWarden*.
- **Windows PC:** download the new `PennyWarden-<version>-windows-x64.exe` (or the zip) and start it. Your data
  folder is renamed by itself at the first start; delete the old program when you no longer want it.
- **Mac:** download the new `.dmg` and drag **PennyWarden** to Applications. macOS sees a new app, so the *Open
  Anyway* step in *Read me first* is needed once more. Your data is found by itself; delete the old app afterwards.
- **Downloads** are now at `github.com/kretherford0983/PennyWarden`. Old links are forwarded.
