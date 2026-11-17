# NMPA Tariff Calculator: real data and validation

Updated 12 Oct 2026.

## What the calculator uses

| Input | Source |
|---|---|
| Every rate | NMPA Indexed SOR w.e.f. 01-05-2026 (`nmpa_public_data/tariff/`) |
| Cargo, quantity, berth, run (C/F), berth hours, receiver | Real past calls from NMPA Daily Vessel Position reports (`data/daily_vessel_position_parsed`, `data/vessel_stays.json`) via `backend/app/services/historical_calls.py` |
| Vessel GRT | Typed in from the vessel's tonnage certificate. It is not in NMPA's reports, so it is never estimated. |
| USD→INR | Typed in: the RBI reference rate on the vessel's entry day (SOR 1.2(iii)) |

The forms have no demo defaults. If GRT or the exchange rate is missing, the affected components are shown as "Needs GRT" or "Needs USD→INR" and left out of the total. The result is then marked **Partial**.

## SOR rules added or fixed in this pass

- **Hourly charges are rounded up.** Berth hire, anchorage and tug hire are charged "per hour or part thereof", so part hours now count as full hours.
- **Vessel status is separate from cargo status.** The vessel's run (C/F) decides whether vessel charges are coastal ₹ or foreign US$. The cargo's status decides the wharfage rate.
- **SPM calls use the SPM tariff (2.6).** Crude at the SPM takes wharfage line A.I.j (₹34.90), not A.I.d (₹96.60). Port dues and pilotage use the SPM rates. SPM tugs are charged for a minimum of 2 hours.
- **PPP berths 14 and 16 are not billed by NMPA.** Wharfage, storage and berth hire there are shown for reference only and are not added to the total, because NMPA's books show only a royalty from these terminals.
- **KIOCL pellets and UPCL coal are flagged.** SOR line B.III.i covers pellets "other than KIOCL", and B.IV.a covers coal "other than UPCL", so neither is priced from those lines.
- **Small craft use their own lines.** Barges, tugs, bunker barges and fishing boats are charged per vessel per hour (2.3.1). Double banking is charged at 50%. Vessels calling only for bunkering at berth have their own berth hire line.
- **Free storage periods can be extended.** Working-day free periods are extended by customs holidays and port non-working days. Coastal cargo is not extended, because its 15 days already include holidays.
- **Bunkering facility charge (3.7) is included**, and the grand total is rounded up to the next rupee (1.2(ix)).
- **NMPA cargo codes are recognised.** Codes from the daily reports, such as IOF, IOP, S.COAL, CSFO, AMSUL, MS/HSD and PHOS.ACID, map to SOR lines. Entries that are not cargo (SPM OP, bunker barge, dredging, crew change) are recognised as such. Cargo names that fit two SOR lines (coal tar pitch, bitumen, raw cashew, plain "coal", fish meal) are flagged for review.

## Checks against past data (`GET /cost/validation`)

1. **2026-27 rates compared with the 2022 SOR.** I compared 115 items with NMPA's SOR general revision of 25-12-2022. Every item has moved by one of two uniform indexation factors: 87 items by ×1.0861 and 28 by ×1.1481. None is out of line, so no transcription errors were found. Separately, all 115 wharfage lines in the code match the 2026 SOR text exactly.
2. **NMPA's own 2023-24 income compared with the SOR.** I divided each income line in NMPA's Revised Estimate for 2023-24 by the tonnage handled that year to get the rate NMPA actually realised per tonne:
   - LPG: ₹240/t, inside the SOR band of ₹213.89 to ₹245.57.
   - POL products: ₹87/t, inside the band of ₹84.14 to ₹96.60.
   - Crude: solving NMPA's two crude wharfage lines at SOR rates gives 158 to 182 lakh tonnes. NMPA reported 168 lakh tonnes, which falls inside that range.
   - Chemicals and other liquids: ₹87/t, inside the band.
   - KIOCL iron ore: ₹49/t, above every SOR iron ore line. This is expected, because the SOR excludes KIOCL pellets.
3. **Past calls compared with the monthly traffic statement.** I summed the tonnage of individual calls in the daily reports for September 2025 to May 2026. It comes to 32.2 Mt, against 37.8 Mt in NMPA's monthly traffic statement (85%). No commodity group goes over the official figure. Fertiliser reaches 99% and F.R.M. 100%. The gap comes from days missing in the report archive and from calls that list no quantity.

## Still open (shown as "Coming soon", never estimated)

The demurrage schedule (3.2.2), storage licence fee, wharf evacuation penalty, shut-out surcharge, container free dwell time, PPP terminal tariffs, volume discount and labour charges. The SOR prints all of these as `*` or refers to another tariff.

## Tests

`python -m pytest tests/test_tariff_calculator.py -q` runs 45 tests. Each expected figure was worked out by hand from the SOR text.
