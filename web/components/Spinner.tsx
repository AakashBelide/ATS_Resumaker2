// A small centered loading spinner used in place of bare "loading…" text across pages.
export default function Spinner({ label = "Loading…", pad = true }: { label?: string; pad?: boolean }) {
  return (
    <div className={`spinner-wrap${pad ? "" : " tight"}`} role="status" aria-live="polite">
      <span className="spinner" aria-hidden />
      <span className="spinner-label">{label}</span>
    </div>
  );
}
