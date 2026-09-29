/** Key moments of the election, as absolute instants.
 *
 *  Written as UTC on purpose. North Vancouver is PDT (UTC-7) on these dates —
 *  daylight time does not end until November 1, 2026 — and a reader in another
 *  timezone should still see a correct countdown. Anything computed from these
 *  must run in the browser: this is a static site, so a value computed at build
 *  time would freeze at whatever it said when the site was last deployed.
 */

export const ADVANCE_OPENS = "2026-10-07T15:00:00Z"; // Oct 7, 8:00 a.m. PDT
export const POLLS_OPEN = "2026-10-17T15:00:00Z"; // Oct 17, 8:00 a.m. PDT
export const POLLS_CLOSE = "2026-10-18T03:00:00Z"; // Oct 17, 8:00 p.m. PDT

export const ELECTION_DAY_LABEL = "Saturday, October 17, 2026";
