/** All-candidates meetings.
 *
 *  Hand-maintained from the District's published list, which it hosts on behalf
 *  of community organisations. The District does not organise or endorse these
 *  events and neither do we; this is a convenience listing with sources.
 *
 *  Past events are kept rather than deleted — a reader arriving late should be
 *  able to tell a meeting happened and go find a recording, not wonder whether
 *  anything was ever held.
 */

export const MEETINGS_VERIFIED = "2026-10-08";
export const MEETINGS_SOURCE =
  "https://www.dnv.org/government-administration/see-who-is-running";

export interface Meeting {
  /** ISO date, used for past/upcoming sorting. */
  date: string;
  time: string;
  location: string;
  host: string;
  hostUrl?: string;
  /** Which races the organiser says the event covers, when stated. */
  covers?: string;
  /** A recording, once the host posts one. Linked, never transcribed: this
   *  site quotes documents it can slice character for character, and a
   *  speech-to-text transcript would put words in a candidate's mouth that
   *  nobody said. The video is the better source anyway. */
  recordingUrl?: string;
  /** Where this host actually posts recordings, for when none exists yet.
   *  Sending someone to a homepage and implying a video is there wastes their
   *  time; this points at the page it would appear on. */
  recordingsAt?: string;
}

export const MEETINGS: Meeting[] = [
  {
    date: "2026-09-24",
    time: "4:30 p.m.",
    location: "Bodwell High School",
    host: "North Vancouver Chamber",
    hostUrl: "https://www.nvchamber.ca/",
    recordingsAt: "https://www.nvchamber.ca/news/",
  },
  {
    date: "2026-10-01",
    time: "7:00 p.m.",
    location: "Eagle Room, Karen Magnussen Community Recreation Centre",
    host: "Lynn Valley Community Association",
    hostUrl: "https://lvca.ca/",
    recordingsAt: "https://lvca.ca/tag/all-candidates-meeting/",
  },
  {
    date: "2026-10-06",
    time: "7:00 p.m.",
    location: "Lynn Valley Library Community Room",
    host: "Better North Shore",
    hostUrl: "https://www.betternorthshore.ca/election2026",
    recordingsAt: "https://www.betternorthshore.ca/election2026",
  },
  {
    date: "2026-10-08",
    time: "7:00 p.m.",
    location: "Mount Seymour United Church",
    host: "Seymour, Blueridge and Deep Cove Community Associations",
    hostUrl: "https://blueridgeca.org/",
  },
  {
    date: "2026-10-13",
    time: "4:45 p.m.",
    location: "Seycove Secondary School",
    host: "Seycove Performance Learning Program",
  },
];
