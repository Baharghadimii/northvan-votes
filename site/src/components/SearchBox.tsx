import { useEffect, useMemo, useRef, useState } from "react";

export interface Passage {
  id: string;        // candidate id
  n: string;         // candidate name
  r: string;         // race label
  inc: boolean;      // incumbent
  c: string;         // category/kind label
  k: "position" | "background";
  q: string;         // the verbatim quote
  u: string;         // source url
  o: boolean;        // from the filed statement
}

interface Props { passages: Passage[] }

function tokens(s: string): string[] {
  return s.toLowerCase().match(/[\w'-]+/g) ?? [];
}

/** Split a quote around the matched terms so they can be marked. */
function highlight(quote: string, terms: string[]) {
  if (!terms.length) return [quote];
  const esc = terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  const re = new RegExp(`(${esc})`, "gi");
  return quote.split(re);
}

export default function SearchBox({ passages }: Props) {
  const [q, setQ] = useState("");
  const [kind, setKind] = useState<"all" | "position" | "background">("all");
  const input = useRef<HTMLInputElement>(null);

  // Adopt ?q= after mounting, not during render, so the server's HTML and the
  // first client render agree.
  useEffect(() => {
    const p = new URLSearchParams(window.location.search).get("q");
    if (p) setQ(p);
    input.current?.focus();
  }, []);

  useEffect(() => {
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q.trim());
    const qs = params.toString();
    window.history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
  }, [q]);

  const terms = useMemo(() => tokens(q), [q]);

  const results = useMemo(() => {
    if (!terms.length) return [];
    const pool = kind === "all" ? passages : passages.filter((p) => p.k === kind);
    return pool
      .map((p) => {
        const hay = `${p.q} ${p.n} ${p.c}`.toLowerCase();
        // Every term must appear: a two-word search should narrow, not widen.
        if (!terms.every((t) => hay.includes(t))) return null;
        const inQuote = terms.filter((t) => p.q.toLowerCase().includes(t)).length;
        return { p, score: inQuote * 10 + (p.o ? 1 : 0) };
      })
      .filter(Boolean)
      .sort((a, b) => b!.score - a!.score)
      .slice(0, 120) as { p: Passage; score: number }[];
  }, [terms, kind, passages]);

  const people = new Set(results.map((r) => r.p.id)).size;

  return (
    <div>
      <div className="search-row">
        <input
          ref={input}
          className="search-input"
          type="search"
          value={q}
          placeholder="wastewater, bike lanes, Harry Jerome, childcare…"
          aria-label="Search everything candidates have said"
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      <div className="search-filters">
        {(["all", "position", "background"] as const).map((k) => (
          <button
            key={k}
            type="button"
            className={`chip${kind === k ? " chip-on" : ""}`}
            aria-pressed={kind === k}
            onClick={() => setKind(k)}
          >
            {k === "all" ? "Everything" : k === "position" ? "What they'd do" : "Who they are"}
          </button>
        ))}
        {["wastewater", "housing", "traffic", "childcare", "taxes", "Harry Jerome"].map((s) => (
          <button key={s} type="button" className="chip chip-suggest" onClick={() => setQ(s)}>
            {s}
          </button>
        ))}
      </div>

      {q.trim() === "" ? (
        <p className="compare-hint">
          Type anything. It searches every word all 59 candidates have said, not
          just their names.
        </p>
      ) : results.length === 0 ? (
        <div className="notice">
          <p>
            Nothing matches “{q.trim()}”. That doesn't mean no candidate cares
            about it — only that none of them wrote the word in what I checked.
          </p>
        </div>
      ) : (
        <>
          <p className="compare-hint">
            {results.length} passage{results.length === 1 ? "" : "s"} from{" "}
            {people} candidate{people === 1 ? "" : "s"}
            {results.length === 120 ? " (showing the first 120)" : ""}.
          </p>
          <div className="grid">
            {results.map(({ p }, i) => (
              <div className="card" key={`${p.id}-${i}`}>
                <div className="candidate-name">
                  <a href={`/candidates/${p.id}/`}>{p.n}</a>
                  {p.inc && <span className="tag tag-incumbent" style={{ marginLeft: 6 }}>Incumbent</span>}
                </div>
                <div className="candidate-meta">{p.r} · {p.c}</div>
                <figure className="quote" style={{ marginInline: 0 }}>
                  <blockquote style={{ margin: 0 }}>
                    {highlight(p.q, terms).map((chunk, j) =>
                      terms.some((t) => chunk.toLowerCase() === t.toLowerCase())
                        ? <mark key={j}>{chunk}</mark>
                        : <span key={j}>{chunk}</span>,
                    )}
                  </blockquote>
                  <figcaption className="source-line">
                    <span className={p.o ? "srctag srctag-official" : "srctag"}>
                      {p.o ? "Filed statement" : "Their campaign site"}
                    </span>
                    <a href={p.u} rel="noopener">source</a>
                  </figcaption>
                </figure>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
