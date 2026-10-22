# Solar claims module

## What is implemented

- The Solar tab accepts a JPG/PNG monitoring screenshot, previews it, and runs the app's existing Tesseract.js OCR in the browser (or Android WebView). Once OCR extracts a valid monthly kWh reading, the image and claim are sent to Supabase automatically; there is no separate confirmation step.
- OCR accepts a kWh value only when it can associate it with a monthly label, or when there is a single kWh value and a report month/year. For inverter dashboards with a **PV production** card, it scopes values to that card, resolves total production from the PV total/components, and excludes the following **Consumption** card. The supplied October 2026 screenshot resolves to **413.00 kWh** (not the 714.00 kWh consumption figure), so confirmation awards **207 points** (0.5 point/kWh, rounded to whole points). Lifetime/cumulative values without clear monthly context are rejected. The supplied screenshot is kept at `tests/fixtures/solar1.jpg` as the regression sample.
- The claim period is prefilled when OCR detects it; otherwise the selected month/year is used. OCR reads visible text and does not independently authenticate the image source or detect edits. Provider verification or signed reports can be added in production.
- Normal claims are awarded immediately at 0.5 point per kWh, rounded to whole points, using the app's existing `points_ledger`. Readings above 50,000 kWh/month are recorded as `flagged_review` and award zero points pending verification. The threshold is configurable in `solar_claims.py` and the SQL RPC.
- The database serializes claims by household/month and has a partial unique index for successful awards. Claim insertion and points-ledger insertion occur in one PostgreSQL transaction; retries cannot award twice.
- Evidence is uploaded to the private `solar-evidence` bucket. The claim stores its household-relative object path.

## Supabase setup

1. For a new setup, run `supabase_solar_claims_migration.sql` in the SQL Editor. For a project that already has the solar RPC, apply `supabase_solar_points_half_rate_migration.sql` to update the award rate. The project must already have its `households`, `household_members`, `points_ledger`, and Auth schemas, plus the existing points-ledger entry-type constraint.
2. Ensure the signed-in account belongs to a household. The storage policy and RPC both check `household_members`; no UI-only restriction is relied upon.
3. Reload the app and open **Solar**. If the migration is missing, the form shows a setup message.

The browser OCR runtime and worker, WASM core, and English traineddata load from version-pinned hosted sources because Flet Studio's asset transport does not expose the bundled scripts as module-loadable worker URLs. OCR therefore requires an internet connection. Android WebView uses the same Tesseract.js version from the CDN. No new Python package is required.

## Points-team integration seam

This repository does not currently contain functions named as Abel's shared points calculator or Ami's earn function. The app's existing canonical award path is the `points_ledger`, already used by the running-rewards RPC. The solar RPC therefore records the award there atomically instead of creating another balance. `calculate_solar_points()` is the Python display/validation adapter, and the SQL calculation is its server-side counterpart. When the team provides the actual shared function signatures, connect them in `solar_claims.py` and replace the SQL RPC's calculation/ledger section; preserve the RPC's transaction, period lock, and duplicate protection.

## Tests

Pure parsing and validation checks are in `tests/test_solar_claims.py` (standard-library `unittest`). From a local project checkout, run:

```text
python -m unittest discover -s tests
```

The database-specific guarantees—same-month duplicate rejection, exactly-once ledger award, and no balance change after a failed RPC—must be exercised against a test Supabase project after applying the migration. The preview cannot reach the authenticated household database unless the browser session and Supabase project are configured.
