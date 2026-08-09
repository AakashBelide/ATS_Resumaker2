"use client";
// Single-select dropdown that shares the MultiSelect panel styling, so every filter dropdown
// looks the same (no native <select> popups that don't match the dark theme).
import { useEffect, useRef, useState } from "react";

type Opt = { value: string; label: string };

export default function Select({ label, value, options, onChange }: {
  label: string;
  value: string;
  options: Opt[];
  onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    function onDoc(e: MouseEvent) { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  const current = options.find((o) => o.value === value) ?? options[0];

  return (
    <div className={`field ms${open ? " open" : ""}`} ref={ref}>
      <label>{label}</label>
      <button type="button" className="ms-btn" onClick={() => setOpen((o) => !o)}>
        <span>{current?.label ?? "—"}</span>
        <span className="ms-caret">▾</span>
      </button>
      {open && (
        <div className="ms-panel">
          <div className="ms-list">
            {options.map((o) => (
              <div key={o.value} className={`ms-opt${o.value === value ? " sel" : ""}`}
                   onClick={() => { onChange(o.value); setOpen(false); }}>
                <span className="ms-opt-l">{o.label}</span>
                {o.value === value && (
                  <span className="ms-check" aria-hidden>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" width="14" height="14"><path d="M20 6L9 17l-5-5" /></svg>
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
