"use client";
// Lightweight SVG donut with a clickable legend, for cross-filtering (Power-BI style):
// clicking a slice/legend row calls onSlice(key); the active slice is emphasized.
const PALETTE = ["#3B74FF", "#34D2E8", "#34e89e", "#F2C24B", "#8FBBFF", "#a78bfa",
  "#ff7a8a", "#5B93FF", "#f472b6", "#5eead4", "#fbbf24", "#c4b5fd"];

export default function Donut({ data, onSlice, active, unit = "" }: {
  data: [string, number][];
  onSlice?: (k: string) => void;
  active?: string;
  unit?: string;
}) {
  const total = data.reduce((a, [, v]) => a + v, 0) || 1;
  const R = 56, SW = 26, C = 2 * Math.PI * R;
  let off = 0;

  return (
    <div className="donut">
      <svg viewBox="0 0 150 150" className="donut-svg" role="img">
        <g transform="rotate(-90 75 75)">
          {data.map(([k, v], i) => {
            const len = (v / total) * C;
            const seg = (
              <circle key={k} cx="75" cy="75" r={R} fill="none"
                      stroke={PALETTE[i % PALETTE.length]} strokeWidth={active && active !== k ? SW - 6 : SW}
                      strokeDasharray={`${len} ${C - len}`} strokeDashoffset={-off}
                      opacity={active && active !== k ? 0.35 : 1}
                      style={{ cursor: onSlice ? "pointer" : "default", transition: "opacity .2s, stroke-width .2s" }}
                      onClick={() => onSlice?.(k)} />
            );
            off += len;
            return seg;
          })}
        </g>
        <text x="75" y="70" textAnchor="middle" className="donut-total">{total}</text>
        <text x="75" y="88" textAnchor="middle" className="donut-unit">{unit}</text>
      </svg>
      <div className="donut-legend">
        {data.map(([k, v], i) => (
          <button key={k} className={`dleg${active === k ? " on" : ""}`} onClick={() => onSlice?.(k)}>
            <span className="dot2" style={{ background: PALETTE[i % PALETTE.length] }} />
            <span className="dleg-k">{k}</span>
            <span className="dleg-v">{v}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
