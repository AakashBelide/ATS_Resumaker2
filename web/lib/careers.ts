// Build a company's careers-page landing URL from its resolved board (source + token + extra).
// Best-effort per ATS; returns "" when we can't construct one (no link shown).
type Board = { source: string; token: string; extra: Record<string, string> };

export function careersUrl(b: Board | undefined): string {
  if (!b) return "";
  const { source, token } = b;
  const e = b.extra || {};
  switch (source) {
    case "greenhouse": return `https://boards.greenhouse.io/${token}`;
    case "lever": return `https://jobs.lever.co/${token}`;
    case "ashby": return `https://jobs.ashbyhq.com/${token}`;
    case "smartrecruiters": return `https://jobs.smartrecruiters.com/${token}`;
    case "workday": return e.host ? `https://${e.host}/${e.site || ""}`.replace(/\/$/, "") : "";
    case "oracle_cloud": return e.host && e.site ? `https://${e.host}/hcmUI/CandidateExperience/en/sites/${e.site}` : "";
    case "icims": return e.host ? `https://${e.host}/jobs/search` : "";
    case "algolia": return e.careers_url || "";   // the original careers page (Algolia host isn't browsable)
    case "amazon": return "https://www.amazon.jobs/en/search";
    case "apple": return "https://jobs.apple.com/en-us/search";
    case "google": return "https://www.google.com/about/careers/applications/jobs/results";
    case "ibm": return "https://www.ibm.com/careers/search";
    default: return e.host ? `https://${e.host}` : "";   // eightfold/jibe/etc. carry the host
  }
}
