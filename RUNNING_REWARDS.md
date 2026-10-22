# Running screenshot uploads

Running screenshots can be submitted at any hour. The limit is **2 successful submissions per account per Malaysia calendar day**. Supabase determines the date and quota, so a device date in UTC+8 cannot be rejected as “in the future” by a UTC database. The database serializes submissions per user/day; simultaneous uploads cannot exceed the limit. A submission is counted when its recognized run details are saved, including a run that earns zero points. To guard against OCR decimal-point errors, the app and submission RPC accept no more than **100 km per screenshot**; higher readings are rejected without awarding points and should be re-uploaded from a clear image.

## Apply the Supabase update

For an existing Supabase project, run `supabase_running_upload_timezone_limit_migration.sql` in that project's SQL Editor, then reload Townly. The app requires the updated quota fields from Supabase before enabling a running screenshot upload. For a fresh project, apply `supabase_running_rewards_migration.sql` instead; it includes the same Malaysia-time behavior.

The photo is processed by the app's existing on-device/browser OCR flow; this update changes the run date and quota enforcement, not photo storage.
