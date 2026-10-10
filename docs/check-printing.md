# Check printing (2.0.0)

PennyWarden can print checks on **printable check stock that already carries the bank numbers** (the MICR line and
the check number are pre-printed). PennyWarden prints the date, the payee, the amount in numbers and in words, the
memo and, when allowed, a signature. It never prints the check number or the bank numbers.

Check printing is an optional module. An **Administrator** sets it up; **Register Users** print checks. Budget
Managers, Budget Users and Auditors have no access to the module (Auditors see the record copy attached to each
printed transaction).

- [For Administrators: setting up](#for-administrators-setting-up)
- [For Register Users: printing a check](#for-register-users-printing-a-check)
- [When something goes wrong](#when-something-goes-wrong)
- [Example: 3-per-page laser checks on an HP LaserJet](#example-3-per-page-laser-checks-on-an-hp-laserjet)

## For Administrators: setting up

### 1. Turn the module on
**System/About → Optional modules → Check Printing module.** *Check Printing* appears in your menu, and Register
Users get a **Print check…** button on withdrawals in the register.

### 2. Create a check style
**Check Printing → New check style from preset → Create.** A check style describes your check stock:

- **the sheet**: how many checks are on a Letter sheet and how you use it — print the top check and tear it off, or
  print each position in turn;
- **the fields**: where the date, payee, amounts, memo and signature print, in inches from the check's top-left
  corner, and the font of each;
- **the feed modes**: how the paper goes into the printer (see below).

The preview shows your fields over a drawing of the stock, with sample data. The grey outline (lines, *PAY TO THE
ORDER OF*, *DOLLARS*, …) is only there to help you place things — it never prints. The shaded strip at the bottom is
the **bank number zone** (the bottom 5/8 inch of the check): nothing may be placed there.

Text sits on the bottom of its box, so a box placed on a pre-printed line puts the writing on the line. Choose
**Long text sample** to see what happens with a long payee name or memo.

### 3. Measure your stock (only if your checks differ from the preset)
With a ruler: the distance from the top of the sheet to each perforation (the check height), and for each field, how
far the pre-printed line is from the check's left and top edges. Enter the numbers, then print the **calibration
page** on plain paper and hold it over a blank check against a light. Move fields by the difference you see.

### 4. Fonts
Checks use only PennyWarden's built-in fonts, so they print the same from any computer:

| Font | Looks like |
|---|---|
| Liberation Sans | Arial |
| Liberation Serif | Times New Roman |
| Liberation Mono | Courier New |
| Carlito | Calibri |

Set a default font and size for the whole check and, if you like, a different one per field. **Print everything in
capitals** is on by default. **Shrink to fit** lets a field's text get smaller (down to its smallest size) before the
user is asked to shorten it.

### 5. Amounts
Both amounts are always calculated from the transaction total — nobody types them. The default is bank convention in
capitals with the protective fill between the words and the cents:

`THREE THOUSAND ONE HUNDRED NINETY-NINE AND ·························· 30/100`

The fill is drawn at the middle height of the letters, so nothing can be written above or below it. The number amount
defaults to `**3,199.30` (thousands commas, no `$` because most stock pre-prints it, two leading asterisks, aligned
right). Each part can be changed under **Amounts**.

### 6. Memo
The **Default memo** is text with optional variables in braces, filled in from the transaction. Type `{` to see the
list:

| Variable | Fills in |
|---|---|
| `{PAYEE}` | payee name |
| `{DATE}` | transaction date |
| `{AMOUNT}` | total, e.g. 3,199.30 |
| `{BUDGET}`, `{BUDGET_CODE}` | budget name / code |
| `{INVOICE}` | invoice number |
| `{DESCRIPTION}` | line description |
| `{NOTES}` | transaction notes |
| `{ORG}` | organization name |
| `{ACCOUNT}` | bank account name (never the number) |

For a split transaction, the line variables give the first value and "and others" (e.g. `48513 and others`).
Names ignore upper/lower case. A name that doesn't exist (`{dtae}`) is refused with a suggestion. To print a brace,
type it twice: `{{` or `}}`.

### 7. Signers and signatures
**Add signer…**: name, title and a signature image (PNG — a scan of the signature on white paper, cropped close;
a transparent background works best). The image is stored **encrypted** and can never be downloaded again; you only
see a small preview marked SAMPLE. It is drawn only on real checks and, when you choose it, on your test prints.
Every print that uses it is recorded in the audit log. Backups include the signature images.

**No signature above this amount** (optional): above it the signature does not print and the check is signed by hand.
The user is told before printing.

### 8. Feed modes
- **Sheet** — the check at the top (or middle, bottom) of a Letter sheet. A sheet with the top check torn off prints
  the same way.
- **Single check** — one check fed through the manual feed on its own, like an envelope. Choose which end goes in
  first (**date end** or **pay-to end**) and the page size:
  - **Letter page** (default; needs no printer setup) with the check placed where the manual-feed guides hold it —
    centered, or against the left or right guide;
  - **Check-sized page**, for printers or printer profiles set up for that size.

Each feed mode has a small **offset** (right/down, up to 1/2 inch) and a **printer note** that users see when they
print (for example which printer profile to choose).

### 9. Test print
**Test print** prints the sample check (marked TEST – NOT A CHECK) in the chosen feed mode; **Calibration page**
prints rulers and where each field starts. Both use your unsaved changes and include a 5-inch line to check the print
scale.

## For Register Users: printing a check

1. In the **Register**, open an active withdrawal and click **Print check…**. (Not offered for deposits, VOID
   transactions or a Closed Fiscal Year.)
2. The first time you print from a bank account, choose its **check style** and how many checks are left on the
   sheet.
3. Check the **feed mode** (the sheet counter suggests one: with one check left it suggests the single-check feed),
   the **signature** and the **memo**. The preview shows exactly what will print.
4. If something doesn't fit, you see the full text and a shortened version: **Use the shortened text** or **Edit it
   myself**. Nothing is cut off without you seeing it.
5. Optional: **Test print on plain paper** and hold it over a blank check against a light.
6. Load the check and **type the number printed on it**. PennyWarden doesn't print the check number, so this keeps
   the register and the bank in agreement. If the transaction has no check number yet, enter it.
7. **Print check**, then **Open the check to print** and print it at **actual size** (see the print settings shown
   for your browser).
8. **Did the check print correctly?**
   - **Yes – done.**
   - **Reprint** — the check came out blank or undamaged (e.g. a jam) and you put the same check back in.
     You give a short reason; the check number stays the same.
   - **Mark spoiled** — the check is damaged or printed in the wrong place. Its number is recorded as a
     **$0.00 VOID record** in the account so it is never used again, and the payment moves to the next check. Keep the
     spoiled check (write VOID on it).

A **record copy** of the check is attached to the transaction: the check as printed, with *SIGNATURE ON FILE:
name* in place of the signature and *COPY – NOT NEGOTIABLE* across it. The transaction shows **Check printed**.

### Your printer settings
If the printing is shifted on your printer, run the **Printer setup assistant** from the print screen:

1. print the 5-inch scale check — if the line isn't exactly 5 inches, the assistant shows the browser setting to fix;
2. print the alignment test the way the check will feed;
3. say what happened (lined up, shifted and by how much, printed smaller, wrong part of the paper, paper-size error,
   nothing printed) and the assistant adjusts and prints again.

These settings are yours only (for that check style and feed mode), up to 1/4 inch, and never change the
Administrator's layout.

## When something goes wrong

| Problem | What to do |
|---|---|
| Everything is a little smaller | The browser is scaling: set **Scale** to **Actual size** / **100%**. Every test page has a 5-inch line to check. |
| Everything is shifted | Run the Printer setup assistant (your printer) or ask an Administrator to set the feed mode's offset (everyone). |
| Single check: printed off the paper | In the assistant choose "printed on the wrong part of the paper" to try the other guide positions. |
| Printer asks for Letter paper / paper-size error | In the assistant choose "paper-size error" to switch between the Letter page and the check-sized page. |
| The browser can't print at actual size | **Download PDF** and print it from a PDF app (Adobe Reader, Preview). |
| Printer jammed but the check is fine | Print again → **Reprint** with a reason. |
| The check is damaged | **Mark spoiled**, then print on the next check. |

Browser settings that matter:

- **Chrome, Brave, Edge:** Scale → *Actual size* (not "Fit to printable area"); check the paper size. To use a
  printer profile saved in your printer driver, click **Print using system dialog** (Ctrl+Shift+P).
- **Firefox:** Scale → *100%*; turn off *Fit to page width*.
- **Safari:** Scale *100%*; turn off *Auto-rotate* and *Scale to fit*.

## Example: 3-per-page laser checks on an HP LaserJet

The preset **3 per page – standard laser (top check first)** was measured from Classic Tan laser 3-up stock: a Letter
sheet with three 3.5-inch checks and a 1/2-inch footer strip.

- **Full sheet, and the 2-check piece** after the top check is torn off: feed mode *Sheet – top check*, Letter, tray
  as usual.
- **Last check:** tear off the footer strip, and feed the check through the manual feed (Tray 1) **date end first**,
  like the stamp edge of an envelope, with the guides against the check. Feed mode *Last check – envelope feed, date
  end first*, Letter page, guides centered.
- The sheet counter (3 → 2 → 1) suggests the right feed mode each time.

*Tip (optional):* if your printer driver lets you save a printing profile (paper size, tray), you can save one for
the single check — a custom 3.5 × 8.5 inch size from the manual feed — and pick it with **Print using system dialog**.
In that case choose the **check-sized page** in your printer settings. This is not needed: the Letter page works
without any printer setup.
