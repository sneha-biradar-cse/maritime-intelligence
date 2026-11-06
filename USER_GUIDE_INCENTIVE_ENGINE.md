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

## Windows note: Poppler is needed only for new statements

The dashboard, the daily-report downloader, the daily-report update and the Excel export work on Windows as they are.
Adding new **NMPA or Ministry statements** (commodity, container, Traffic & Performance, Ministry reports) also needs the free
**Poppler** tools (`pdftotext`). If they are missing, the update stops, changes nothing, and says so. To install on Windows:
download the latest `Release-...zip` from https://github.com/oschwartz10612/poppler-windows/releases, unzip it to `C:\poppler`,
add the folder containing `pdftotext.exe` (for example `C:\poppler\Library\bin`) to the PATH, and open a new terminal.
