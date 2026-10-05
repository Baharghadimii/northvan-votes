import raw from "~/data/candidates.json";
import taxonomy from "~/data/taxonomy.json";

export type Municipality = "cnv" | "dnv";
export type Office = "mayor" | "council" | "trustee";

export interface Source {
  type: "official_statement" | "campaign_site";
  url: string;
  title: string | null;
  text: string;
  retrieved: string;
}

export interface Position {
  category: string;
  flashpoints: string[];
  quote: string;
  source_url: string;
  source_type: Source["type"];
  char_start: number;
  char_end: number;
}

export interface Candidate {
  id: string;
  name: string;
  surname: string;
  municipality: Municipality;
  office: Office;
  incumbent: boolean;
  photo_url: string | null;
  email: string | null;
  phone: string | null;
  website: string | null;
  socials: Record<string, string>;
  nomination_docs: string[];
  financial_disclosure: string[];
  sources: Source[];
  positions: Position[];
  /** Who they are and what they have done, rather than what they would do. */
  background: Position[];
}

export interface Category {
  id: string;
  label: string;
  description: string;
  /** Hue that tints this topic's card. Identifies a subject, not a position. */
  hue: number;
}

export interface Flashpoint {
  id: string;
  label: string;
  description: string;
}

export const candidates = raw as Candidate[];
export const categories = taxonomy.categories as Category[];
export const flashpoints = taxonomy.flashpoints as Flashpoint[];
export const backgroundKinds = (taxonomy as any).background as Category[];

export const MUNICIPALITIES: Record<Municipality, string> = {
  cnv: "City of North Vancouver",
  dnv: "District of North Vancouver",
};

export const MUNICIPALITIES_SHORT: Record<Municipality, string> = {
  cnv: "City",
  dnv: "District",
};

export const OFFICES: Record<Office, string> = {
  mayor: "Mayor",
  council: "Council",
  trustee: "School Trustee",
};

/** Seats being filled, so a page can say "you pick six". */
export const SEATS: Record<string, number> = {
  "cnv-mayor": 1,
  "cnv-council": 6,
  "cnv-trustee": 3,
  "dnv-mayor": 1,
  "dnv-council": 6,
  "dnv-trustee": 4,
};

export interface Race {
  key: string;
  municipality: Municipality;
  office: Office;
  label: string;
  seats: number;
  candidates: Candidate[];
}

/** Ballot order is meaningful, so races are always rendered in a fixed order. */
const RACE_ORDER: Array<[Municipality, Office]> = [
  ["cnv", "mayor"],
  ["cnv", "council"],
  ["cnv", "trustee"],
  ["dnv", "mayor"],
  ["dnv", "council"],
  ["dnv", "trustee"],
];

export function races(pool: Candidate[] = candidates): Race[] {
  return RACE_ORDER.map(([municipality, office]) => {
    const key = `${municipality}-${office}`;
    return {
      key,
      municipality,
      office,
      label: `${MUNICIPALITIES[municipality]} — ${OFFICES[office]}`,
      seats: SEATS[key],
      candidates: pool.filter(
        (c) => c.municipality === municipality && c.office === office,
      ),
    };
  }).filter((r) => r.candidates.length > 0);
}

export function categoryById(id: string): Category | undefined {
  return categories.find((c) => c.id === id);
}

export function backgroundKindById(id: string): Category | undefined {
  return backgroundKinds.find((b) => b.id === id);
}

export function flashpointById(id: string): Flashpoint | undefined {
  return flashpoints.find((f) => f.id === id);
}

export function candidateById(id: string): Candidate | undefined {
  return candidates.find((c) => c.id === id);
}

/** Candidates with at least one tagged position in a category. */
export function speakingOn(categoryId: string, pool: Candidate[] = candidates) {
  return pool.filter((c) => c.positions.some((p) => p.category === categoryId));
}

export function positionsFor(candidate: Candidate, categoryId: string) {
  return candidate.positions.filter((p) => p.category === categoryId);
}

/** Categories ranked by how many candidates have addressed them. */
export function categoriesByCoverage() {
  return categories
    .map((c) => ({ ...c, count: speakingOn(c.id).length }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

export function sourceFor(candidate: Candidate, url: string): Source | undefined {
  return candidate.sources.find((s) => s.url === url);
}

/** Deterministic shuffle. Used at build time so the no-JS order is not
 *  alphabetical; the client reshuffles per session on top of this. */
export function seededShuffle<T>(items: T[], seed: number): T[] {
  const out = [...items];
  let s = seed >>> 0;
  const next = () => {
    // xorshift32
    s ^= s << 13; s >>>= 0;
    s ^= s >> 17;
    s ^= s << 5; s >>>= 0;
    return s / 0xffffffff;
  };
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(next() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

export const BUILD_SEED = 20261017;

export function formatDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-CA", {
    year: "numeric", month: "long", day: "numeric",
  });
}

export const ELECTION_DAY = "2026-10-17";

/** Candidates whose campaign site could not be read, and why. Their pages are
 *  thinner than others' for reasons that have nothing to do with them, so the
 *  page says so instead of leaving a silence the reader would misread. */
export const UNREADABLE_SITES: Record<string, string> = {
  "dnv-mayor-little-mike":
    "The address the District lists for them is a Facebook page, which I don't scrape — and as of October 5 it does not load at all: Facebook reports the content as unavailable.",
  "dnv-council-muri-lisa":
    "The website on their nomination form redirects to a Facebook page that requires a login, which I won't scrape.",
};
