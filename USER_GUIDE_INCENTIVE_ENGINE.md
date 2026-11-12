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
| **Plan a discount** and **Schemes** | Plan a discount: what would a discount or rebate cost? A draft proposal for one customer (PDF). Schemes: NMPA's schemes in force, the scheme register, past results, other ports. Approval and tracking of schemes. | Traffic, Finance, approving authority |

## A typical week for a Traffic officer (15 minutes)

1. **Start here:** read the actions for Traffic.
2. **Customers & cargo → Protect key customers:** check the customers with a warning sign.
3. **Call the customer**, then open **"Record what you learned"** (same section) and save the owner, the reason, the stage and
   a follow-up date. It also appears in Trade Intelligence, Customers.
4. Only if price is the confirmed reason: **Plan a discount → Customer proposal**. Check the options and download the
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

## Discount calculator and scheme register (November 2026 update)

- **Baseline = actual tonnes in the last 12 months** (from NMPA's monthly statements), shown above the cards with the
  three earlier financial years. It is no longer this year's months scaled up, which was wrong for seasonal cargo
  (iron ore was understated by about 30%).
- **"What if…?" table, from real data:** no extra cargo; your estimate; winning back last year's share of all major
  ports (Ministry of Ports figures, split between linked cargos); getting back to NMPA's best recent year; break-even;
  your target. Every row says where its figure comes from.
- **What research and other Indian ports show:** sourced notes on how shippers react to port charges, the national
  40% coastal concession, Mormugao's and Deendayal's schemes, and Cochin's design rules.
- **Scheme register:** start from one of NMPA's own designs (iron ore rebate, quiet months, Harit-style slabs,
  customer commitment); new baseline method "previous financial year, pro rata" as in NMPA's iron ore notice; the
  expected cost of the scheme from real tonnes; and a "ready for review" checklist of seven items.
- **How other major ports design schemes** (Schemes tab): 14 kinds of scheme, whether NMPA's own notices show
  each one, examples at other major ports with their sources (`data/other_ports_schemes.csv`), and what each suggests
  for NMPA. Legal basis: Section 27(1) of the Major Port Authorities Act, 2021 and the Tariff Policy 2021.
- New register template: larger ships only (parcel size). The approval reference field asks for the Board resolution
  and the trade notice.

## Layout (November 2026)

Five tabs, each answering one question: **Start here** (what to do this week), **What we earn**, **Customers & cargo**
(who and what is at risk, and why), **Plan a discount** (calculator, customer proposal, rules) and **Schemes** (NMPA's
schemes in force, scheme register, past results, other major ports for reference). The register states which cargo and
discount from *Plan a discount* its designs use.

## What's new (November 2026): did it work, stopping tricks, ship charges, one budget

Think of the port as a shop and a discount as a sale. The Incentive Engine already worked out what a sale costs. These
additions answer the next questions: **did the sale actually work, is anyone cheating it, and what do all our sales cost
together?** Every answer is written in plain sentences on screen.

| What | Where in the dashboard | What it tells you |
|---|---|---|
| **Did a discount work?** | Schemes → *Did a discount work? Compare with the other major ports* | If NMPA's cargo rose 15% but the same cargo rose 12% at every other major port, only the 3% gap is credited to the discount. It also shows NMPA's **normal ups and downs**: a gap inside that range is not evidence the discount worked. Each scheme in the register gets this check automatically. |
| **Checks for gaming** | Plan a discount → deal desk (shown with every proposal and in its PDF), and *Check a customer for gaming* | Six checks: holding cargo back before a discount starts; squeezing cargo into the last month; moving cargo between related companies; switching coastal/foreign labels; moving cargo from a private (PPP) berth onto an NMPA berth; a baseline that is too easy to beat. A warning is a reason to look, not proof. |
| **Ship charges** | Plan a discount → *Ship charges: what a ship pays* | A ship's bill from NMPA's Scale of Rates: entry fee (port dues), pilot and tugs (pilotage), berth rent (berth hire). Also what NMPA's own container (35% / 50%) and Cape-size (30%) rebates cost, once ship sizes are known (see below). |
| **One budget for all discounts** | Schemes → *All discounts together: one budget* | What every approved and active scheme could cost, against the port's wharfage income, and how many schemes are actually bringing extra cargo. The Board can set a total cap and a ceiling for combining discounts (approver role only). Until it does, nothing changes: discounts cannot be combined, as before. |
| **Year-end settlement** | Deal desk → *Save as draft scheme* (record the tonnes the customer promises), then Schemes → *Year-end settlement* | Like a loyalty card: if the customer misses its promise, the rebate is reduced in proportion, or not paid at all, whichever rule was agreed. If the discount was already given on each bill, the tool shows how much to recover. |
| **"Please don't leave" offer** | Deal desk options | A discount on all of a customer's cargo to keep it. The tool shows the break-even: e.g. a 10% offer is worth it only if the chance of losing the cargo without it is above about 11%. |
| **More ideas from other ports** | Schemes → *How other major ports design schemes* | Now 28 schemes, including Rotterdam, Antwerp, Valencia, Long Beach and Chennai's 2026-27 scheme, each with its source. |

### One thing only NMPA can give: each ship's size

Ship charges depend on a ship's size (its **GRT**), and NMPA's daily reports do not contain it. The GRT is printed on every
port-dues bill. Put it in `data/vessel_gt.csv` (one row per ship: name, IMO number if known, GRT, bill reference) and the
container and Cape-size rebate costs work themselves out. Sizes from NMPA's bills always win over any other source.

### Public data, fetched with one script

```
python scripts/fetch_public_incentive_data.py vessel-gt     ship sizes from Wikidata (a free public register; well-known ships only)
python scripts/fetch_public_incentive_data.py fx            US dollar to rupee rates (ECB rates, marked as estimates)
python scripts/fetch_public_incentive_data.py fx --rbi-file rates.csv    RBI/FBIL reference rates you downloaded (official)
python scripts/fetch_public_incentive_data.py other-ports   copies of other ports' scheme documents, for reference
python scripts/fetch_public_incentive_data.py all --dry-run see what would be fetched, without saving anything
```

Ship sizes from Wikidata are matched by name, so they are marked "planning only". Once at least 8 ships have both a known
size and a length in the daily reports, the tool can also **estimate** the size of other ships from their length, and labels
it as an estimate. Only sizes from NMPA's bills can support an official proposal.

### Related companies

`data/customer_groups.csv` lists customers that belong together, each with its evidence: for example Paradeep Phosphates and
Mangalore Chemicals & Fertilizers (merged October 2025). Add a row only when there is evidence: a filing, a notice or NMPA's
confirmation.

## Merged additions (12 November 2026)

- **Schemes → Every NMPA scheme, judged so far.** One table of NMPA's schemes and how each is doing against the other
  major ports. The full check ("Did a discount work?", just below it) is used wherever it covers the cargo; coal and
  containers, which it does not cover yet, get a simple check, labelled as such. Schemes still running update as the
  Ministry publishes new months; schemes whose cargo the Ministry does not show separately say "Cannot be measured".
- **Plan a discount → Pay only when the customer is ready.** From the daily vessel reports: how many ship calls would
  qualify for a rebate paid only when the ship did not wait because the customer was not ready (waiting for a berth
  never counts against the customer). A matching template is in the scheme register.

## Decision aids (12 November 2026)

- **Plan a discount → under the "What if…" table: growth check.** A discount on all cargo pays for itself only if
  customers bring discount ÷ (1 − discount) more cargo a year (10% → 11.1%). The cards show how often NMPA's cargo of
  that type grew that much in a year without the discount (every twelve-month period since 2022), and its usual yearly
  change. Example: LPG grew 11.1% in 5 of 35 periods, so a 10% discount on all LPG is a long shot.
- **Schemes → Schemes ending soon: review before they lapse.** Every scheme in force (and every approved scheme in the
  register) ending within six months, with how it is doing against the other major ports, its cost where it can be
  priced, and a renew / change / stop recommendation. A broad check of a whole cargo group never gives a firm stop.
  The Start here card "NMPA schemes in force" says how many need their review planned.
- **Schemes → Scheme register → open a scheme → Board agenda note / Trade notice (Word, draft).** Drafts built from the
  scheme's own figures: purpose, background, proposal, cost and break-even, safeguards, legal basis (Section 27(1)),
  resolution sought; and a trade notice in NMPA's usual form. For Traffic and Finance to check before the Board meeting.
