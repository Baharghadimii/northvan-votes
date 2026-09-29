/** Voting logistics, transcribed from each municipality's own election pages.
 *
 *  Hand-maintained on purpose: it is a handful of dates that must be exactly
 *  right, and a scraper that silently drifts would be worse than a file someone
 *  re-checks. Re-verify against the two source URLs before every deploy and
 *  update `verified`.
 */

export const VERIFIED = "2026-09-29";

export interface VotingPlace { name: string; address: string; note?: string }
export interface AdvanceDay { date: string; hours: string; places: VotingPlace[] }

export interface MunicipalityVoting {
  name: string;
  short: string;
  source: string;
  contact: { phone: string; email: string };
  advance: AdvanceDay[];
  generalDay: { hours: string; places: VotingPlace[] };
  special?: string;
  extras: string[];
}

export const VOTING: Record<"cnv" | "dnv", MunicipalityVoting> = {
  cnv: {
    name: "City of North Vancouver",
    short: "City",
    source:
      "https://www.cnv.org/City-Hall/General-Local-Election/2026-General-Local-Election",
    contact: { phone: "604-220-1361", email: "elections@cnv.org" },
    advance: [
      { date: "Wednesday, October 7", hours: "8:00 a.m. – 8:00 p.m.", places: [{ name: "City Hall", address: "141 West 14th Street" }] },
      { date: "Saturday, October 10", hours: "10:00 a.m. – 4:00 p.m.", places: [{ name: "City Hall", address: "141 West 14th Street" }] },
      { date: "Tuesday, October 13", hours: "10:00 a.m. – 7:00 p.m.", places: [{ name: "City Hall", address: "141 West 14th Street" }] },
      { date: "Wednesday, October 14", hours: "8:00 a.m. – 8:00 p.m.", places: [{ name: "City Hall", address: "141 West 14th Street" }] },
      { date: "Thursday, October 15", hours: "10:00 a.m. – 6:00 p.m.", places: [{ name: "City Hall", address: "141 West 14th Street" }] },
    ],
    generalDay: {
      hours: "8:00 a.m. – 8:00 p.m.",
      places: [
        { name: "Larson Elementary School (Gym)", address: "2605 Larson Road", note: "curbside" },
        { name: "Carson Graham Secondary School (Small Gym)", address: "2145 Jones Avenue", note: "curbside" },
        { name: "Westview Elementary School (Gym)", address: "641 West 17th Street", note: "curbside" },
        { name: "Queen Mary Elementary School (Gym)", address: "230 West Keith Road", note: "curbside" },
        { name: "Ridgeway Elementary School (Gym)", address: "420 East 8th Street", note: "curbside" },
        { name: "Sutherland Secondary School (Gym)", address: "1860 Sutherland Avenue", note: "curbside" },
        { name: "Harry Jerome Community Recreation Centre", address: "130 East 23rd Street" },
        { name: "John Braithwaite Community Centre (Shoreline Room)", address: "145 West 1st Street" },
        { name: "Pipe Shop", address: "115 Victory Ship Way" },
      ],
    },
    extras: [
      "Curbside voting during advance voting is on 13th Street in front of City Hall.",
      "Mail ballots had to be applied for by October 1, so that option has closed.",
    ],
  },

  dnv: {
    name: "District of North Vancouver",
    short: "District",
    source: "https://www.dnv.org/government-administration/voting-dates-and-locations",
    contact: { phone: "604-990-2311", email: "elections@dnv.org" },
    advance: [
      { date: "Wednesday, October 7", hours: "8:00 a.m. – 8:00 p.m.", places: [{ name: "District Hall", address: "355 West Queens Road" }] },
      {
        date: "Saturday, October 10",
        hours: "8:00 a.m. – 8:00 p.m.",
        places: [
          { name: "Parkgate Community Centre", address: "3625 Banff Court" },
          { name: "District Hall", address: "355 West Queens Road" },
        ],
      },
      {
        date: "Monday, October 12",
        hours: "8:00 a.m. – 8:00 p.m.",
        places: [
          { name: "Parkgate Community Centre", address: "3625 Banff Court" },
          { name: "District Hall", address: "355 West Queens Road" },
        ],
      },
    ],
    generalDay: {
      hours: "8:00 a.m. – 8:00 p.m.",
      places: [
        { name: "Argyle Secondary School", address: "1131 Frederick Road" },
        { name: "Blueridge Elementary School", address: "2650 Bronte Drive" },
        { name: "Brooksbank Elementary School", address: "980 East 13th Street" },
        { name: "Canyon Heights Elementary School", address: "4501 Highland Boulevard" },
        { name: "Capilano Elementary School", address: "1230 West 20th Street" },
        { name: "Carisbrooke Elementary School", address: "510 East Carisbrooke Road" },
        { name: "Cleveland Elementary School", address: "1255 Eldon Road" },
        { name: "Eastview Elementary School", address: "1801 Mountain Highway" },
        { name: "Handsworth Secondary School", address: "1033 Handsworth Road" },
        { name: "Highlands Elementary School", address: "3150 Colwood Drive" },
        { name: "Lions Gate Community Recreation Centre", address: "1733 Lions Gate Lane" },
        { name: "Lynn Creek Community Recreation Centre", address: "1491 Hunter Street" },
        { name: "Lynnmour Elementary School", address: "800 Forsman Avenue" },
        { name: "Montroyal Elementary School", address: "5310 Sonora Drive" },
        { name: "Mountainside Secondary School", address: "3365 Mahon Avenue" },
        { name: "Norgate Elementary School", address: "1295 Sowden Street" },
        { name: "Parkgate Community Centre", address: "3625 Banff Court" },
        { name: "Ross Road Elementary School", address: "2875 Bushnell Place" },
        { name: "Seycove Secondary School", address: "1204 Caledonia Avenue" },
        { name: "Sherwood Park Elementary School", address: "4085 Dollar Road" },
        { name: "Upper Lynn Elementary School", address: "1540 Coleman Street" },
        { name: "Windsor Secondary School", address: "931 Broadview Drive" },
      ],
    },
    special:
      "A special voting opportunity runs Saturday, October 10, 9:00 a.m. – 4:00 p.m. at Lions Gate Hospital (231 East 15th Street) for inpatients at Lions Gate Hospital, North Shore Hospice and the HOpe Centre.",
    extras: [
      "Curbside voting, priority access and other assistance are available at District voting places.",
    ],
  },
};
