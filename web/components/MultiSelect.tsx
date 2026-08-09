"use client";
// Searchable, scrollable, multi-select dropdown. Replaces the native <select> for long lists
// (e.g. 77 companies) whose native popup overflowed the viewport. The panel is a fixed-height
// scroll area anchored to the control, closes on outside-click, and reports the chosen values.
import { useEffect, useRef, useState } from "react";

type Opt = [string, number]; // [value, count]

export default function MultiSelect({ label, options, selected, onChange, labelFor }: {
  label: string;
  options: Opt[];
  selected: string[];
  onChange: (v: string[]) => void;
  labelFor?: (v: string) => string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const disp = (v: string) => (labelFor ? labelFor(v) : v);
  const shown = q ? options.filter(([v]) => disp(v).toLowerCase().includes(q.toLowerCase())) : options;
  const toggle = (v: string) =>
    onChange(selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v]);
  const summary = selected.length === 0 ? "any"
    : selected.length === 1 ? disp(selected[0]) : `${selected.length} selected`;

  return (
    <div className={`field ms${open ? " open" : ""}`} ref={ref}>
      <label>{label}</label>
      <button type="button" className="ms-btn" onClick={() => setOpen((o) => !o)}>
        <span className={selected.length ? "" : "muted"}>{summary}</span>
        <span className="ms-caret">▾</span>
      </button>
      {open && (
        <div className="ms-panel">
          <div className="ms-top">
            <input className="ms-search" autoFocus placeholder="search…" value={q}
                   onChange={(e) => setQ(e.target.value)} />
            {selected.length > 0 && (
              <button className="ms-clear" onClick={() => onChange([])}>clear</button>
            )}
          </div>
          <div className="ms-list">
            {shown.length === 0 && <div className="ms-empty">no matches</div>}
            {shown.map(([v, n]) => (
              <label key={v} className="ms-opt">
                <input type="checkbox" checked={selected.includes(v)} onChange={() => toggle(v)} />
                <span className="ms-opt-l">{disp(v)}</span>
                <span className="ms-opt-n">{n}</span>
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
