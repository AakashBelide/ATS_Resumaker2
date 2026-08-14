"use client";
// Profile (RA.3): the profile signals + preferences the match uses, plus enrichment
// proposals mined from tracked jobs (view-only here; accept via CLI `profile set`).
import { useEffect, useState } from "react";
import Spinner from "@/components/Spinner";

import { profileDocument, profileProposals, profileSummary, savePreferences, type ProfileBullet, type ProfileDocument, type ProfileSummary, type Proposal } from "@/lib/api";
import { groupSkills } from "@/lib/skills";

const bulletText = (b: ProfileBullet) => (typeof b === "string" ? b : b?.text ?? "");

export default function ProfilePage() {
  const [p, setP] = useState<ProfileSummary | null>(null);
  const [doc, setDoc] = useState<ProfileDocument | null>(null);
  const [raw, setRaw] = useState(false);
  const [prop, setProp] = useState<{ have_but_unlisted: Proposal[]; recurring_gaps: Proposal[] } | null>(null);
  const [error, setError] = useState("");
  const [prefEdit, setPrefEdit] = useState(false);
  const [prefTarget, setPrefTarget] = useState("");
  const [prefAvoid, setPrefAvoid] = useState("");
  const [prefSaved, setPrefSaved] = useState<"" | "saving" | "saved">("");

  useEffect(() => {
    profileSummary().then(setP).catch((e) => setError(String(e)));
    profileDocument().then(setDoc).catch(() => {});
    profileProposals().then(setProp).catch(() => {});
  }, []);

  useEffect(() => {   // seed the preference editor from the loaded summary
    if (!p) return;
    const pr = (p.preferences ?? {}) as Record<string, unknown>;
    const a = (k: string) => (Array.isArray(pr[k]) ? (pr[k] as string[]) : []);
    setPrefTarget(a("target_roles").join(", "));
    setPrefAvoid(a("avoid_roles").join(", "));
  }, [p]);

  async function savePrefs() {
    const csv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
    setPrefSaved("saving");
    try {
      const saved = await savePreferences({ target_roles: csv(prefTarget), avoid_roles: csv(prefAvoid) });
      setP((prev) => (prev ? { ...prev, preferences: { ...(prev.preferences ?? {}), ...saved } } : prev));
      setPrefSaved("saved"); setTimeout(() => setPrefSaved(""), 2000); setPrefEdit(false);
    } catch (e) { setError(String(e)); setPrefSaved(""); }
  }

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
        {!p ? <Spinner /> : (
          <>
            <div className="stat-row">
              <div className="stat"><div className="num">{p.years_experience}</div><div className="cap">Years experience</div></div>
              <div className="stat"><div className="num accent">{p.n_skills}</div><div className="cap">Skills on file</div></div>
              <div className="stat"><div className="num">{p.needs_sponsorship ? "YES" : "NO"}</div><div className="cap">Needs sponsorship</div></div>
              <div className="stat"><div className="num">{p.employers.length}</div><div className="cap">Employers</div></div>
            </div>

            <div className="block" id="preferences">
              <div className="block-head"><h2>Preferences</h2>
                <button className="btn btn-sm" style={{ marginLeft: "auto" }} onClick={() => setPrefEdit((v) => !v)}>
                  {prefEdit ? "cancel" : "edit"}
                </button>
              </div>
              {prefEdit ? (
                <div className="panel">
                  <p className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
                    These drive the <b>on-target</b> filter in Discovery and matching. Comma-separated.
                  </p>
                  <div className="filters" style={{ marginBottom: 12 }}>
                    <div className="field"><label>target roles</label>
                      <input value={prefTarget} onChange={(e) => setPrefTarget(e.target.value)} placeholder="ai, ml, software engineer" /></div>
                    <div className="field"><label>avoid roles</label>
                      <input value={prefAvoid} onChange={(e) => setPrefAvoid(e.target.value)} placeholder="sales, manager" /></div>
                  </div>
                  <button className="btn btn-sm btn-primary" onClick={savePrefs} disabled={prefSaved === "saving"}>
                    {prefSaved === "saving" ? "saving…" : prefSaved === "saved" ? "saved ✓" : "save"}
                  </button>
                </div>
              ) : (
                <div className="panel kv">
                  <span className="k">Target roles</span>
                  <span className="chips">{arr("target_roles").length ? arr("target_roles").map((r) => <span key={r} className="chip">{r}</span>) : <span className="muted" style={{ fontSize: 13 }}>none set</span>}</span>
                  <span className="k">Avoid roles</span>
                  <span className="chips">{arr("avoid_roles").length ? arr("avoid_roles").map((r) => <span key={r} className="chip">{r}</span>) : <span className="muted" style={{ fontSize: 13 }}>none set</span>}</span>
                </div>
              )}
            </div>

            {(p.employers.length > 0 || p.titles.length > 0) && (
              <div className="block">
                <div className="block-head"><h2>Experience</h2><span className="count">{p.employers.length} employers</span></div>
                <div className="panel kv">
                  <span className="k">Employers</span>
                  <span className="chips">{p.employers.map((e) => <span key={e} className="chip">{e}</span>)}</span>
                  <span className="k">Titles</span>
                  <span className="chips">{p.titles.map((t) => <span key={t} className="chip">{t}</span>)}</span>
                </div>
              </div>
            )}

            <div className="block">
              <div className="block-head"><h2>Skills</h2><span className="count">{p.n_skills} · grouped</span></div>
              <div className="panel skill-groups">
                {groupSkills(p.skills).map(([cat, items]) => (
                  <div className="skill-group" key={cat}>
                    <div className="sg-head"><span className="sg-name">{cat}</span><span className="sg-n">{items.length}</span></div>
                    <div className="chips">{items.map((s) => <span key={s} className="chip skill">{s}</span>)}</div>
                  </div>
                ))}
              </div>
            </div>

            {doc && (
              <div className="block">
                <div className="block-head"><h2>Full profile</h2>
                  <span className="count">{(doc.projects?.length ?? 0)} projects · {(doc.experience?.length ?? 0)} roles</span>
                  <button className="btn btn-sm" style={{ marginLeft: "auto" }} onClick={() => setRaw((v) => !v)}>
                    {raw ? "readable" : "raw JSON"}
                  </button>
                </div>
                {raw ? (
                  <pre className="json-view">{JSON.stringify(doc, null, 2)}</pre>
                ) : (
                  <div className="panel">
                    {doc.summary && (
                      <div className="doc-sec"><div className="kicker">Summary</div><p className="doc-summary">{doc.summary}</p></div>
                    )}
                    {(doc.experience?.length ?? 0) > 0 && (
                      <div className="doc-sec"><div className="kicker">Experience</div>
                        {doc.experience!.map((e, i) => (
                          <div className="doc-item" key={i}>
                            <div className="doc-item-head">
                              <span className="doc-title">{e.title}{e.organization ? ` · ${e.organization}` : ""}</span>
                              <span className="mono muted">{[e.start_date, e.is_current ? "present" : e.end_date].filter(Boolean).join(" – ")}</span>
                            </div>
                            <ul className="doc-bullets">{(e.bullets ?? []).map((b, j) => <li key={j}>{bulletText(b)}</li>)}</ul>
                          </div>
                        ))}
                      </div>
                    )}
                    {(doc.projects?.length ?? 0) > 0 && (
                      <div className="doc-sec"><div className="kicker">Projects</div>
                        {doc.projects!.map((pr, i) => (
                          <div className="doc-item" key={i}>
                            <div className="doc-item-head">
                              <span className="doc-title">{pr.title}{pr.organization ? ` · ${pr.organization}` : ""}</span>
                              <span className="mono muted">{pr.date}</span>
                            </div>
                            <ul className="doc-bullets">{(pr.bullets ?? []).map((b, j) => <li key={j}>{bulletText(b)}</li>)}</ul>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

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
