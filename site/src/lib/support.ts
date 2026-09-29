/** Reader support link.
 *
 *  Set BMC_USERNAME to the handle in your Buy Me a Coffee URL — for
 *  buymeacoffee.com/baharg that is "baharg". While it is empty the button does
 *  not render anywhere, so the site never ships a dead donate link.
 *
 *  Two things this must never become, because the site's credibility rests on
 *  them being true (see /methodology):
 *
 *    1. Money from anyone running in this election, or campaigning for or
 *       against someone in it. Refund it if it arrives.
 *    2. A reason to change what the site says. Nothing here is for sale:
 *       not placement, not ordering, not a quote, not a correction.
 */

export const BMC_USERNAME = "";

export const SUPPORT_BLURB =
  "This is free, has no ads, and tracks nobody. It costs a domain and a few " +
  "evenings. If it helped you vote, you can buy me a coffee.";

export function supportUrl(): string | null {
  return BMC_USERNAME ? `https://www.buymeacoffee.com/${BMC_USERNAME}` : null;
}
