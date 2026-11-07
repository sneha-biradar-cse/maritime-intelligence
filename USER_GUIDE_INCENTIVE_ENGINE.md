# Incentive Engine: a short guide for New Mangalore Port's team

The Incentive Engine helps the port decide **where an incentive might help, what it would cost, and whether it worked**,
using NMPA's own published data. It does not give discounts by itself: every decision stays with NMPA's approval process.

## Where to start

Open **Incentive Engine → Start here**. It lists **this week's actions**, worked out from the data each time the page loads:
who should act, why (with the numbers), and where in the tool to look. Download the **one-page Incentive brief (PDF)** to share
with management.

## The four tabs

| Tab | Answers | Used mostly by |
|---|---|---|
| **Start here** | What should we do this week? How is the module measured (baseline KPIs)? | Everyone |
| **What we earn** | How much wharfage each cargo and each customer brings; does it match NMPA's accounts? | Finance, management |
| **Customers & cargo** | Which key customers are at risk? Which cargo is going to other ports? Which months are quiet? How do our rates compare with Cochin? | Traffic / marketing |
| **Proposals & schemes** | What would a discount or rebate cost? A draft proposal for one customer (PDF). Approval and tracking of schemes. | Traffic, Finance, approving authority |

## A typical week for a Traffic officer (15 minutes)

1. **Start here:** read the actions for Traffic.
2. **Customers & cargo → Protect key customers:** check the customers with a warning sign.
3. **Call the customer**, then open **"Record what you learned"** (same section) and save the owner, the reason, the stage and
   a follow-up date. It also appears in Trade Intelligence, Customers.
4. Only if price is the confirmed reason: **Proposals & schemes → Customer proposal**. Check the options and download the
   one-page PDF, then use **"Save this proposal as a draft scheme"**.
5. **Scheme register** (same tab): Traffic review → Finance review → approval with an order or file reference → Active. While
   it runs, the register shows the customer's own cargo against the baseline agreed at the start.

## Words used

- **Wharfage:** the port's charge on every tonne of cargo loaded or unloaded.
- **Scale of Rates:** NMPA's official price list; its rates are ceilings, so the port may charge less or give rebates.
- **Traced tonnes:** cargo matched to a named customer in NMPA's daily vessel reports (about 85% of official tonnes).
- **Baseline:** the cargo a customer would bring without any benefit; agreed and frozen before a scheme starts.
- **Rebate on extra volume:** money back only on cargo above the baseline; existing cargo keeps the full rate.
- **Statistical gap:** cargo New Mangalore would have handled had it kept last year's share; a reason to ask, not proof.

## What the figures are, and are not

Money figures are **estimates** from NMPA's published tonnes and Scale of Rates, checked against NMPA's published accounts.
They are not billing figures. Items marked **Pending NMPA data** become measured once NMPA shares billing and confirmations.
Full detail on every source and assumption: `DATA_SOURCES_AND_ASSUMPTIONS.md`.

## Tables and files

Every table can be downloaded as a CSV file (hover over it, icons at the top right). Customer proposals and the brief download
as one-page PDFs.

## Demo mode and pilot mode

**Demo mode** (as shipped): no users are set up. Anyone can try every feature, but recorded actions are not attributable to a
person, so they are not for real decisions. The top of the dashboard says so.

**Pilot mode**: switch it on by adding the first user. Every action that changes data then needs a login, and the backend
checks each person's role on every action (hiding a button is not enough). The audit trail records the logged-in person.

```
python scripts\manage_users.py add ravi "R. Kumar" traffic        (asks for a password, at least 10 characters)
python scripts\manage_users.py add srao "S. Rao" finance
python scripts\manage_users.py add amenon "A. Menon" approver
python scripts\manage_users.py add md "Managing Director" viewer
python scripts\manage_users.py list
python scripts\manage_users.py remove ravi
```

| Role | Can do |
|---|---|
| traffic | Record customer owners, reasons and follow-ups; respond to alerts; create draft schemes; send them to Finance; mark them active or completed; request amendments |
| finance | Review schemes and send them back; respond to alerts |
| approver | Approve or reject schemes (with an order or file reference) |
| viewer | See everything, change nothing |

Passwords are stored only as salted hashes in `data/users.json`. Restart the backend after adding or removing users.

## Getting the daily vessel reports and one Excel file

With NMPA's permission for automated download (the site otherwise asks programs not to crawl it):

```
python scripts\download_daily_reports.py --dry-run          (lists what it finds on NMPA's archive; downloads nothing)
python scripts\download_daily_reports.py                    (downloads only the missing days, 3 seconds apart, into incoming\)
python scripts\download_daily_reports.py --from 2026-10-27 --to 2026-11-30   (a date range)
python scripts\update_trade_data.py                         (reads and checks each new PDF, then refreshes everything)
python scripts\export_daily_reports_excel.py                (one workbook: output\NMPA_daily_vessel_reports.xlsx)
```

`data\download_log.csv` records, for every date wanted, the link found and the result (downloaded, already held, not found on
the archive, or failed and why). The workbook has one row per ship per report day (berthed, waiting, expected), each with its
date, source PDF and whether that day is checked against its original.

## The PDF text tools (Poppler): installed automatically

The checks on NMPA and Ministry statements read the PDFs with Poppler, a free and widely used set of PDF text tools
(pdftotext, pdfinfo, pdftoppm). Windows does not include it, so `scripts\refresh_all.py` installs it the first time a new
statement arrives, into the project's own folder (`tools\poppler`): a pinned version from its official release page, with
its SHA-256 fingerprint checked before use (a file that does not match is refused and deleted). Nothing outside the project
folder is changed. To install it by hand instead: `python scripts\setup_poppler.py`.

### What the harvester does with older or unclear statements

- Statements for months already in the data (for example container statements from 2019 to September 2026) are downloaded
  to `nmpa_public_data\harvested\older_statements\` and kept for history. They are never fed to the update automatically,
  because older layouts can differ; they can be added deliberately after checking.
- A statement whose title does not say the month is downloaded and its month is read from inside the PDF. If it is newer
  than the data held, it goes to the update; otherwise to the archive. A month is never guessed.

## Keeping the data current with one command

With NMPA's permission for automated download:

```
python scripts\refresh_all.py --dry-run      (shows what would be downloaded; changes nothing)
python scripts\refresh_all.py                (does everything below, in order)
```

1. **NMPA documents** (`scripts\harvest_nmpa_documents.py`): reads NMPA's public pages (statistics, reports, trade notices
   and circulars, port tariff, downloads, office memorandums), lists every PDF in `data\harvest_catalog.csv`, and downloads
   only documents not held yet. Monthly statements go to `incoming\` for the update; notices, tariffs and reports go to
   `nmpa_public_data\harvested\` for a person to read. Notices whose title mentions a rebate, incentive, concession,
   discount or waiver are listed at the end as "read these". It also reads the Ministry of Ports' publication page
   (shipmin.gov.in, TRW publication): Major Ports monthly reports for months not held go to `incoming\` for the update.
2. **Daily vessel reports** since the last one held.
3. **The update**: checks every new file and refreshes all figures (all-or-nothing).
4. **The Excel workbook** of daily reports.

Then restart the backend so the dashboard shows the new data.

### Run it automatically every Monday at 7:00 (Windows Task Scheduler)

In PowerShell (once):

```
schtasks /Create /SC WEEKLY /D MON /ST 07:00 /TN "NMPA data refresh" /TR "C:\nmpa\maritime\venv\Scripts\python.exe C:\nmpa\maritime\scripts\refresh_all.py"
```

To remove it: `schtasks /Delete /TN "NMPA data refresh" /F`. The computer must be on at that time.
