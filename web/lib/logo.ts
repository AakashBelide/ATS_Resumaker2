// Best-effort company branding for cards/tables. Logos come from DuckDuckGo's keyless icon
// service via a domain guessed from the company name (curated overrides for the ambiguous
// ones). The <img> onError in the UI swaps to a lettered monogram, so a missing/wrong domain
// degrades gracefully — no network dependency is load-bearing.

const OVERRIDES: Record<string, string> = {
  "JPMC - Chase": "jpmorganchase.com",
  "American Express": "americanexpress.com",
  "Bank of America": "bankofamerica.com",
  "ByteDance/TikTok": "tiktok.com",
  "State Street": "statestreet.com",
  "Morgan Stanley": "morganstanley.com",
  "Wells Fargo": "wellsfargo.com",
  "Goldman Sachs": "goldmansachs.com",
  "McKinsey & Company": "mckinsey.com",
  "Vertex Pharmaceuticals": "vrtx.com",
  "Dassault Systemes": "3ds.com",
  "T-Mobile": "t-mobile.com",
  "TD Bank": "td.com",
  "Citizens Bank": "citizensbank.com",
  "Bracebridge Capital": "bracebridgecapital.com",
  MITRE: "mitre.org",
  X: "x.com",
  IBM: "ibm.com",
  AMD: "amd.com",
  HP: "hp.com",
  PwC: "pwc.com",
  BCG: "bcg.com",
  RBC: "rbc.com",
  WHOOP: "whoop.com",
  Neo4j: "neo4j.com",
  LendBuzz: "lendbuzz.com",
};

export function companyDomain(name: string): string {
  if (OVERRIDES[name]) return OVERRIDES[name];
  const slug = name
    .toLowerCase()
    .replace(/\b(inc|llc|ltd|corp|corporation|company|co|group|holdings|technologies|labs)\b/g, "")
    .replace(/&/g, "and")
    .replace(/[^a-z0-9]/g, "");
  return slug ? `${slug}.com` : "";
}

export function logoUrl(name: string): string {
  const d = companyDomain(name);
  return d ? `https://icons.duckduckgo.com/ip3/${d}.ico` : "";
}

export function monogram(name: string): string {
  const parts = name.replace(/[^A-Za-z0-9 ]/g, " ").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

// Mirrors the backend `title_level` (src/resumaker/ingestion/service.py) so a per-card level
// badge stays consistent with the Discovery level facet. Deterministic, keyword-based.
const LEVELS: [string, RegExp][] = [
  ["intern", /\bintern(ship)?\b|\bco[-\s]?op\b|\bapprentice/],
  ["manager", /\b(manager|mgr|director|head of|vp|vice president)\b/],
  ["staff", /\b(staff|principal|distinguished|fellow|architect)\b/],
  ["senior", /\b(senior|sr|lead)\b/],
  ["junior", /\b(junior|jr|entry[-\s]level|new[-\s]grad|graduate|early career)\b/],
];
export function titleLevel(title: string): string {
  const t = (title || "").toLowerCase();
  for (const [level, re] of LEVELS) if (re.test(t)) return level;
  return "mid";
}
