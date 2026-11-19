/** Official results of the October 17, 2026 election.
 *
 *  Hand-transcribed from each municipality's own declared results, never from
 *  news coverage, and kept in `data/results.json` keyed by candidate id. Each
 *  row also keeps the name exactly as the official source prints it, so anyone
 *  can line the two up.
 *
 *  The checks at the bottom run at build time. A missing candidate, a name
 *  that does not match, or a race with the wrong number of winners throws,
 *  which fails the build, and deploy.sh refuses to upload a failed build.
 */

import raw from "~/data/results.json";
import { candidates, SEATS, type Candidate, type Municipality } from "~/lib/data";

export const RESULTS_VERIFIED = "2026-11-19";

export interface Result {
  official_name: string;
  votes: number;
  elected: boolean;
}

export interface ResultsSource {
  name: string;
  /** The page that lists every candidate's official vote count. */
  url: string;
  label: string;
  /** The formal declaration, where it is a separate document. */
  declarationUrl?: string;
  declared: string;
  officer: string;
}

export const RESULTS_SOURCES: Record<Municipality, ResultsSource> = {
  cnv: {
    name: "City of North Vancouver",
    url: "https://www2.cnv.org/election2026/",
    label: "City of North Vancouver official election results",
    declared: "October 21, 2026",
    officer: "Amelia Cifarelli, Chief Election Officer",
  },
  dnv: {
    name: "District of North Vancouver",
    url: "https://www.dnv.org/government-administration/2026-election-results",
    label: "District of North Vancouver official election results",
    declarationUrl: "https://docs.dnv.org/documents/declaration-of-official-results.pdf",
    declared: "October 19, 2026",
    officer: "Genevieve Lanz, Chief Election Officer",
  },
};

export const RESULTS = raw as Record<string, Result>;

export function resultFor(c: Candidate): Result {
  return RESULTS[c.id];
}

export function isElected(c: Candidate): boolean {
  return RESULTS[c.id]?.elected === true;
}

export function formatVotes(n: number): string {
  return `${n.toLocaleString("en-CA")} ${n === 1 ? "vote" : "votes"}`;
}

/** Winners in a race, most votes first. */
export function electedIn(pool: Candidate[]): Candidate[] {
  return pool
    .filter(isElected)
    .sort((a, b) => RESULTS[b.id].votes - RESULTS[a.id].votes);
}

// ---- build-time checks ----------------------------------------------------

const letters = (s: string) =>
  s.normalize("NFKD").toLowerCase().replace(/[^a-z]/g, "");

const problems: string[] = [];
for (const c of candidates) {
  const r = RESULTS[c.id];
  if (!r) {
    problems.push(`no official result for ${c.id}`);
    continue;
  }
  if (letters(r.official_name).length !== letters(c.name).length ||
      !letters(r.official_name).includes(letters(c.surname))) {
    problems.push(`${c.id}: official name "${r.official_name}" does not match "${c.name}"`);
  }
}
for (const id of Object.keys(RESULTS)) {
  if (!candidates.some((c) => c.id === id)) problems.push(`result for unknown candidate ${id}`);
}
for (const [race, seats] of Object.entries(SEATS)) {
  const won = candidates.filter(
    (c) => `${c.municipality}-${c.office}` === race && isElected(c),
  ).length;
  if (won !== seats) problems.push(`${race}: ${won} marked elected, ${seats} seats`);
}
if (problems.length) {
  throw new Error("Official results do not line up:\n  " + problems.join("\n  "));
}
