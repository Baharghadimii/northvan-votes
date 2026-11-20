/** Promises and votes: each council's campaign words next to its votes.
 *
 *  `votes.json` is written by pipeline/build_votes.py and holds only votes a
 *  person has approved in data/vote-review.yaml: the issue match, the
 *  plain-language summary and, for the City, each member's vote as read from
 *  the minutes, are all that person's call. Everything here is presentation.
 */

import raw from "~/data/votes.json";
import chamber from "~/data/chamber.json";
import {
  candidateById, categories, type Candidate, type Category, type Municipality,
} from "~/lib/data";
import { resultFor } from "~/lib/results";

export type Decision = "for" | "against" | "absent" | "n/a";

export interface Vote {
  id: string;
  municipality: Municipality;
  source_kind: "district_table" | "city_minutes";
  date: string;
  item_number: string;
  title: string;
  meeting_type: string;
  result: string;
  resolution_text: string;
  minutes_url: string | null;
  video_url: string | null;
  members: Record<string, Decision>;
  minutes_adopted?: boolean;
  summary: string;
  issues: string[];
}

export interface MuniStatus {
  retrieved: string;
  source_page: string;
  awaiting_review: number;
  held_back: number;
  no_motion: { id: string; date: string; title: string; meeting_type: string }[];
  procedural: number;
  meetings_read: string[];
}

const DATA = raw as unknown as {
  term_start: string;
  members: Record<Municipality, string[]>;
  status: Record<Municipality, MuniStatus>;
  published: Vote[];
};

export const TERM_START = DATA.term_start;
export const VOTES = DATA.published;
export const STATUS = DATA.status;

/** Each new council, mayor first, then councillors by votes received. */
export function membersOf(m: Municipality): Candidate[] {
  return DATA.members[m]
    .map((id) => {
      const c = candidateById(id);
      if (!c) throw new Error(`votes.json names unknown member ${id}`);
      return c;
    })
    .sort((a, b) =>
      a.office !== b.office
        ? a.office === "mayor" ? -1 : 1
        : resultFor(b).votes - resultFor(a).votes,
    );
}

export const ALL_MEMBERS: Candidate[] = [...membersOf("cnv"), ...membersOf("dnv")];

export const SOURCE_LABEL: Record<Municipality, string> = {
  cnv: "the City's council minutes",
  dnv: "the District's Council voting decisions table",
};

export const DECISION_LABEL: Record<Decision, string> = {
  for: "Voted for",
  against: "Voted against",
  absent: "Absent",
  "n/a": "N/A in the record",
};

export function votesBy(c: Candidate): Vote[] {
  return VOTES.filter((v) => v.members[c.id] !== undefined);
}

export function votesOn(c: Candidate, issue: string): Vote[] {
  return votesBy(c).filter((v) => v.issues.includes(issue));
}

/** The Chamber of Commerce asked two questions; each maps to one issue. */
const CHAMBER_ISSUES = ["transportation", "local-economy"] as const;

export interface ChamberReply {
  issue: string;
  question: string;
  answer: string;
  pdf: string;
}

export function chamberReplies(c: Candidate): ChamberReply[] {
  const m = (chamber as any).municipalities[c.municipality];
  const a = m?.answers.find((x: any) => x.candidate_id === c.id);
  if (!a) return [];
  return CHAMBER_ISSUES.map((issue, i) => ({
    issue,
    question: (chamber as any).questions[i] as string,
    answer: (a[`answer${i + 1}`] ?? "") as string,
    pdf: a.pdf as string,
  })).filter((r) => r.answer.trim().length > 0);
}

export interface IssueRow {
  cat: Category;
  quotes: Candidate["positions"];
  chamber: ChamberReply[];
  votes: Vote[];
}

/** Every issue where this member said something or has a matched vote. */
export function issueRows(c: Candidate): IssueRow[] {
  const replies = chamberReplies(c);
  return categories
    .map((cat) => ({
      cat,
      quotes: c.positions.filter((p) => p.category === cat.id),
      chamber: replies.filter((r) => r.issue === cat.id),
      votes: votesOn(c, cat.id),
    }))
    .filter((r) => r.quotes.length + r.chamber.length + r.votes.length > 0);
}
