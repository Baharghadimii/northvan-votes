import { useEffect, useMemo, useState } from "react";

export interface CompareCandidate {
  id: string;
  name: string;
  incumbent: boolean;
  race: string;
  sortkey: string;
  hasStatement: boolean;
  /** category id -> the verbatim quotes tagged to it */
  byCategory: Record<string, string[]>;
}

export interface CompareRace {
  key: string;
  label: string;
  seats: number;
}

interface Props {
  candidates: CompareCandidate[];
  racesList: CompareRace[];
  categories: { id: string; label: string }[];
}

const MAX = 6;

export default function CompareGrid({ candidates, racesList, categories }: Props) {
  // Render the same thing the server did, then adopt the URL after mounting.
  // Reading window during render makes the first client render disagree with
  // the server's HTML, which React rejects as a hydration mismatch.
  const [race, setRace] = useState(racesList[0]?.key ?? "");
  const [selected, setSelected] = useState<string[]>([]);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get("race");
    if (fromUrl && racesList.some((r) => r.key === fromUrl)) setRace(fromUrl);
    const ids = (params.get("ids") ?? "").split(",").filter(Boolean);
    if (ids.length) setSelected(ids.slice(0, MAX));
    setHydrated(true);
  }, [racesList]);

  // Keep the URL in step so a comparison can be sent to someone else. Held
  // until the URL has been read, or this would erase an incoming link.
  useEffect(() => {
    if (!hydrated) return;
    const params = new URLSearchParams();
    params.set("race", race);
    if (selected.length) params.set("ids", selected.join(","));
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  }, [race, selected, hydrated]);

  const inRace = useMemo(
    () => candidates.filter((c) => c.race === race).sort((a, b) => a.sortkey.localeCompare(b.sortkey)),
    [candidates, race],
  );

  const chosen = useMemo(
    () => inRace.filter((c) => selected.includes(c.id)),
    [inRace, selected],
  );

  function toggle(id: string) {
    setSelected((prev) =>
      prev.includes(id)
        ? prev.filter((x) => x !== id)
        : prev.length >= MAX
          ? prev
          : [...prev, id],
    );
  }

  function changeRace(next: string) {
    setRace(next);
    setSelected([]);
  }

  // Only show rows where at least one chosen candidate said something, so the
  // grid does not fill with empty cells.
  const rows = categories.filter((cat) =>
    chosen.some((c) => (c.byCategory[cat.id] ?? []).length > 0),
  );

  const raceMeta = racesList.find((r) => r.key === race);

  return (
    <div>
      <div className="compare-controls">
        <label>
          <span>Race</span>
          <span className="select-wrap">
            <select value={race} onChange={(e) => changeRace(e.target.value)}>
              {racesList.map((r) => (
                <option key={r.key} value={r.key}>{r.label}</option>
              ))}
            </select>
          </span>
        </label>
        <p className="compare-hint">
          {raceMeta && raceMeta.seats > 1
            ? `You elect ${raceMeta.seats} in this race. `
            : ""}
          Pick up to {MAX} candidates to compare
          {selected.length > 0 ? ` — ${selected.length} selected` : ""}.
        </p>
      </div>

      <div className="chip-row">
        {inRace.map((c) => {
          const on = selected.includes(c.id);
          const full = !on && selected.length >= MAX;
          return (
            <button
              key={c.id}
              type="button"
              className={`chip${on ? " chip-on" : ""}`}
              aria-pressed={on}
              disabled={full}
              title={full ? `Deselect one first (maximum ${MAX})` : undefined}
              onClick={() => toggle(c.id)}
            >
              {c.name}
              {c.incumbent && <em> · incumbent</em>}
              {!c.hasStatement && <em> · no statement</em>}
            </button>
          );
        })}
      </div>

      {selected.length > 0 && (
        <p className="compare-hint">
          <button type="button" className="linky" onClick={() => setSelected([])}>
            Clear selection
          </button>
        </p>
      )}

      {chosen.length === 0 ? (
        <div className="notice"><p>Choose candidates above to see them side by side.</p></div>
      ) : rows.length === 0 ? (
        <div className="notice">
          <p>
            None of the selected candidates has a recorded position on any topic.
            {chosen.some((c) => !c.hasStatement)
              ? " Some of them have not published a statement."
              : ""}
          </p>
        </div>
      ) : (
        <div className="compare-scroll">
          <table className="compare">
            <caption className="visually-hidden">
              Candidate positions by issue. Quotes are verbatim.
            </caption>
            <thead>
              <tr>
                <th scope="col" className="corner">Issue</th>
                {chosen.map((c) => (
                  <th scope="col" key={c.id}>
                    <a href={`/candidates/${c.id}/`}>{c.name}</a>
                    {c.incumbent && <span className="tag tag-incumbent">Incumbent</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((cat) => (
                <tr key={cat.id}>
                  <th scope="row">
                    <a href={`/issues/${cat.id}/`}>{cat.label}</a>
                  </th>
                  {chosen.map((c) => {
                    const quotes = c.byCategory[cat.id] ?? [];
                    return (
                      <td key={c.id}>
                        {quotes.length === 0 ? (
                          <span className="nothing">Not addressed</span>
                        ) : (
                          quotes.map((q, i) => (
                            <blockquote key={i}>{q}</blockquote>
                          ))
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
