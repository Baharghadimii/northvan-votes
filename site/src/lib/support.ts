/** Reader support link.
 *
 *  Set BMC_USERNAME to the handle in your Buy Me a Coffee URL — for
 *  buymeacoffee.com/baharg that is "baharg". While it is empty the button does
 *  not render anywhere, so the site never ships a dead donate link.
 *
 *  The site makes no public claim either way about what this earns. If anyone
 *  asks, answer them directly — saying nothing on the page is not a commitment
 *  to secrecy.
 */

export const BMC_USERNAME = "baharehgh";

export const SUPPORT_BLURB =
  "Free to use, no ads, nothing tracking you around the web. If it helped " +
  "you work out your ballot, you can buy me a coffee.";

export function supportUrl(): string | null {
  return BMC_USERNAME ? `https://www.buymeacoffee.com/${BMC_USERNAME}` : null;
}
