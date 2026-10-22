# MyRewards

The Rewards destination uses the signed-in Supabase account as the shared wallet. Voucher history/status is stored in `myrewards_vouchers`, and catalogue redemption debits the same `points_ledger` used for walking and solar awards. SharedPreferences is only a cache; an offline or failed cloud write is not treated as a successful redemption. QR cashier scanning is still simulated in-app.

## Supabase setup / upgrade

Run `supabase_myrewards_migration.sql` in the SQL Editor of the same Supabase project used by both phone and web app, then reload Townly on each device. It creates the shared voucher RPCs and ledger debit path, and adds the required `reward_redemption` ledger entry type. The app imports existing local vouchers into Supabase the next time that user signs in; existing points should come from the database ledger (the old local 124-point starter display is no longer authoritative).

## Add a reward

1. Add an object to the `rewards` array in `reward_catalog.json` with a unique `id`, brand, title, description, `imageUrl`, `pointsCost`, `valueLabel`, category, `validDays`, `termsList`, `restrictions`, and `active` flag. Keep point costs and RM values in this file so they are easy to edit.
2. Add the product banner SVG under `assets/` and set `imageUrl` to its filename. Set `logoUrl` to the brand's official website favicon URL so the actual logo appears in the catalogue badge; if omitted or unavailable, the badge falls back to brand initials.
3. To issue the reward through a promo code, add a code-to-reward-ID entry under `promoCodes`.

Standard voucher terms are in `standardTerms`; reward-specific conditions belong in that reward's `termsList`. The Sime Darby parking conditions are already listed on its reward.

Solar earning is now 0.5 point per kWh, rounded to whole points. For a project whose solar RPC is already installed, apply `supabase_solar_points_half_rate_migration.sql` in the connected Supabase SQL editor so server awards use the updated rate too.
