"use client";
// Profile (RA.3): the profile signals + preferences the match uses, plus enrichment
// proposals mined from tracked jobs (view-only here; accept via CLI `profile set`).
import { useEffect, useState } from "react";

import { profileProposals, profileSummary, type ProfileSummary, type Proposal } from "@/lib/api";

export default function ProfilePage() {
  const [p, setP] = useState<ProfileSummary | null>(null);
  const [prop, setProp] = useState<{ have_but_unlisted: Proposal[]; recurring_gaps: Proposal[] } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    profileSummary().then(setP).catch((e) => setError(String(e)));
    profileProposals().then(setProp).catch(() => {});
  }, []);

  const prefs = (p?.preferences ?? {}) as Record<string, unknown>;
  const arr = (k: string) => (Array.isArray(prefs[k]) ? (prefs[k] as string[]) : []);

  return (
    <>
      <header className="topbar">
        <div>
          <div className="kicker">Profile</div>
          <h1 style={{ marginTop: 6 }}>Your profile</h1>
        </div>
        <div className="topbar-spacer" />
        {p && <span className="mono muted">{p.years_experience} yrs · {p.n_skills} skills</span>}
      </header>

      <div className="page">
        {error && <p className="error">{error}</p>}
        {!p ? <p className="loading">loading…</p> : (
          <>
            <div className="stat-row">
              <div className="stat"><div className="num">{p.years_experience}</div><div className="cap">Years experience</div></div>
              <div className="stat"><div className="num accent">{p.n_skills}</div><div className="cap">Skills on file</div></div>
              <div className="stat"><div className="num">{p.needs_sponsorship ? "YES" : "NO"}</div><div className="cap">Needs sponsorship</div></div>
              <div className="stat"><div className="num">{p.employers.length}</div><div className="cap">Employers</div></div>
            </div>

            <div className="block">
              <div className="block-head"><h2>Preferences</h2></div>
              <div className="panel kv">
                <span className="k">Target roles</span>
                <span className="chips">{arr("target_roles").map((r) => <span key={r} className="chip">{r}</span>)}</span>
                <span className="k">Avoid roles</span>
                <span className="chips">{arr("avoid_roles").map((r) => <span key={r} className="chip">{r}</span>)}</span>
              </div>
            </div>

            <div className="block">
              <div className="block-head"><h2>Skills</h2><span className="count">{p.n_skills}</span></div>
              <div className="panel"><div className="chips">{p.skills.map((s) => <span key={s} className="chip">{s}</span>)}</div></div>
            </div>

            {prop && (
              <div className="block">
                <div className="block-head"><h2>Enrichment proposals</h2><span className="count">mined from tracked jobs</span></div>
                <div className="panel">
                  <p className="kicker" style={{ marginBottom: 10 }}>Have but unlisted · safe to add</p>
                  {prop.have_but_unlisted.length === 0 ? <p className="muted" style={{ fontSize: 13 }}>none yet</p> :
                    prop.have_but_unlisted.map((x, i) => (
                      <div className="prop" key={i}>
                        <span className="cnt">{x.count}×</span>
                        <div><div className="req">{x.requirement}</div><div className="cos">{x.companies.join(", ")}</div></div>
                      </div>
                    ))}
                  <p className="kicker" style={{ margin: "18px 0 10px" }}>Recurring gaps · verify before adding</p>
                  {prop.recurring_gaps.length === 0 ? <p className="muted" style={{ fontSize: 13 }}>none yet</p> :
                    prop.recurring_gaps.map((x, i) => (
                      <div className="prop" key={i}>
                        <span className="cnt" style={{ color: "var(--gold)", background: "rgba(242,194,75,0.08)", borderColor: "rgba(242,194,75,0.25)" }}>{x.count}×</span>
                        <div><div className="req">{x.requirement}</div><div className="cos">{x.companies.join(", ")}</div></div>
                      </div>
                    ))}
                  <p className="muted mono" style={{ fontSize: 11, marginTop: 16 }}>accept a proposal with: resumaker profile set …</p>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
