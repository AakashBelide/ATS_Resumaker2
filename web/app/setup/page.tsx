// Setup docs page (public, `/setup`, RB.3). Anthropic/OpenAI-style two-part guide (Local + Cloud)
// with a sticky side-nav, code blocks, and callouts. Mirrors the repo's SETUP.md; the runnable
// scripts (run-local.sh / bootstrap.sh) and the paste-into-a-CLI SETUP_SKILL.md live in the repo.
import Link from "next/link";
import type { ReactNode } from "react";

function Code({ children }: { children: string }) {
  return <pre className="doc-pre"><code>{children}</code></pre>;
}
function Note({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" }) {
  return <div className={`doc-callout ${tone}`}>{children}</div>;
}
const NAV = [
  ["prereqs", "Prerequisites"], ["profile", "Your profile"], ["disclaimers", "Disclaimers"],
  ["model", "Model selection"], ["local", "A. Local (Docker)"], ["cloud", "B. Self-hosting (cloud)"],
  ["extension", "Browser extension"], ["troubleshooting", "Troubleshooting"],
];

export default function SetupPage() {
  return (
    <div className="doc">
      <div className="glow-bg" />
      <header className="doc-topbar">
        <Link href="/" className="doc-brand">
          <span className="rail-hex" aria-hidden>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 2l8.66 5v10L12 22l-8.66-5V7L12 2z" /></svg>
          </span>
          <b>ATS Resumaker</b>
        </Link>
        <nav className="doc-topnav">
          <a className="doc-navlink doc-navicon" href="https://github.com/AakashBelide/ATS_Resumaker2" target="_blank" rel="noreferrer" title="View on GitHub" aria-label="GitHub">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" width="18" height="18"><path d="M9 19c-4 1.5-4-2-5-2.5M15 21v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.3 4.3 0 0 0-.1-3.2s-1-.3-3.5 1.3a12 12 0 0 0-6.2 0C6.9 2.1 5.9 2.4 5.9 2.4a4.3 4.3 0 0 0-.1 3.2A4.6 4.6 0 0 0 4.5 8.8c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21" /></svg>
          </a>
          <Link className="btn btn-sm btn-primary" href="/login">Login</Link>
        </nav>
      </header>

      <div className="doc-layout">
        <aside className="doc-side">
          <p className="doc-side-h mono">On this page</p>
          {NAV.map(([id, label]) => <a key={id} href={`#${id}`} className="doc-side-link">{label}</a>)}
        </aside>

        <main className="doc-main">
          <p className="doc-kicker mono">Self-host guide</p>
          <h1 className="doc-h1">Set up ATS Resumaker</h1>
          <p className="doc-lead">
            Run it two ways: <b>Local (Docker)</b> on your machine, or <b>Self-hosting (cloud)</b> on
            Cloud Run + Turso + Vercel within their free tiers. Start local to try it; go cloud when
            you want it always-on (needed for the extension + email digest).
          </p>
          <Note>
            The full, always-current version of this guide is <code>SETUP.md</code> in the repo, with a
            paste-into-any-CLI <code>SETUP_SKILL.md</code> that can walk you through, and run, these
            steps. The scripts referenced below (<code>scripts/run-local.sh</code>,{" "}
            <code>scripts/bootstrap.sh</code>) live there too.
          </Note>

          <section id="prereqs">
            <h2 className="doc-h2">Prerequisites</h2>
            <table className="doc-table">
              <thead><tr><th>Tool</th><th>For</th></tr></thead>
              <tbody>
                <tr><td><b>git</b></td><td>cloning the repo</td></tr>
                <tr><td><b>Docker + Compose</b></td><td>local run (required)</td></tr>
                <tr><td><b>uv</b></td><td>Python runtime (CLI/dev)</td></tr>
                <tr><td><b>Node 20+</b></td><td>the web dashboard</td></tr>
                <tr><td><b>Claude CLI</b></td><td>the default LLM engine (subscription)</td></tr>
                <tr><td><b>gcloud, Terraform 1.6+, Turso CLI</b></td><td><i>cloud only</i></td></tr>
              </tbody>
            </table>
          </section>

          <section id="profile">
            <h2 className="doc-h2">Your profile is the source of truth</h2>
            <p>Everything generated traces to <code>data/profile/profile.json</code>, your real
              employers, titles, metrics, and skills. <b>Create it before onboarding or generating.</b>
              Hand-write it from the schema, or use the in-app <b>Profile chat agent</b>, which
              interviews you and proposes entries you approve (the easiest bootstrap for a new user).
              <code>data/</code> is gitignored PII, it never leaves your machine/bucket.</p>
          </section>

          <section id="disclaimers">
            <h2 className="doc-h2">Disclaimers</h2>
            <ul className="doc-list">
              <li><b>Cost:</b> the cloud path fits free tiers (Cloud Run 240k/450k, Turso 3 GB, GCS
                5 GB, Scheduler 3 jobs, Actions 2000 min, Vercel hobby). Attach billing to GCP and set
                a <b>$1 budget alert</b> anyway.</li>
              <li><b>Claude CLI OAuth = personal use only.</b> <code>claude setup-token</code> is for
                <i> your</i> subscription; running it on a shared/hosted server may breach ToS + hit
                rate limits. For a real hosted instance use the metered Anthropic API
                (<code>RESUMAKER_DEFAULT_PROVIDER=anthropic</code> + <code>ANTHROPIC_API_KEY</code>).</li>
              <li><b>Human-in-the-loop:</b> it advises and drafts; it never auto-applies.</li>
            </ul>
          </section>

          <section id="model">
            <h2 className="doc-h2">Choosing the Claude model</h2>
            <p>Model is env-selectable, pick per your subscription/usage:</p>
            <Code>{`RESUMAKER_MODEL_FAST=claude-haiku-4-5        # cheap extraction
RESUMAKER_MODEL_STANDARD=claude-sonnet-4-5   # analysis / match
RESUMAKER_MODEL_QUALITY=claude-opus-4-8      # tailoring`}</Code>
            <p className="muted">Lower-usage plan? A <b>budget preset</b> (Sonnet standard+quality,
              Haiku fast) keeps quality high at lower cost.</p>
          </section>

          <section id="local">
            <h2 className="doc-h2">A. Local (Docker)</h2>
            <p>Runs entirely on your machine, SQLite, in-process worker, local storage. Docker required.</p>
            <Code>{`# 1) Clone + configure
git clone <your-fork-url> ats-resumaker && cd ats-resumaker
cp .env.example .env          # set RESUMAKER_API_TOKEN=$(openssl rand -hex 24)

# 2) Put your profile at data/profile/profile.json (see "Your profile")

# 3) Bring it up (api + worker; LibreOffice + Claude CLI baked into the worker image)
./scripts/run-local.sh        # docker compose -f deploy/docker-compose.split.yml up --build
# API -> http://localhost:8000

# 4) The dashboard (separate terminal)
cd web && cp .env.local.example .env.local
#   set API_ORIGIN=http://localhost:8000, API_TOKEN=<same token>,
#   LOGIN_USERNAME / LOGIN_PASSWORD / SESSION_SECRET (openssl rand -hex 32)
npm install && npm run dev    # http://localhost:3000`}</Code>
          </section>

          <section id="cloud">
            <h2 className="doc-h2">B. Self-hosting (cloud)</h2>
            <p><b>Do the account setup in this order:</b></p>
            <ol className="doc-list">
              <li><b>Google Cloud</b>, create a project, <b>enable billing</b>, $1 budget alert,
                region <code>us-central1</code>.</li>
              <li><b>Turso</b>, create a DB; grab its URL (<code>libsql://...</code>) + auth token.</li>
              <li><b>Resend</b>, sign up <b>with the SAME email you want the digest delivered to</b>
                (free tier only sends to your own verified address). Create an API key.</li>
              <li><b>Vercel</b>, sign up (GitHub login); you'll deploy <code>web/</code> here.</li>
              <li><b>GitHub</b>, fork the repo; Actions deploy on push to <code>main</code>.</li>
            </ol>
            <Note tone="warn">
              The <b>Resend same-email</b> detail is easy to miss, on the free tier the digest
              silently won't arrive unless the recipient is your Resend account email.
            </Note>
            <p>Interactive auth (can't be scripted):</p>
            <Code>{`gcloud auth login
gcloud auth application-default login
gcloud config set project <YOUR_PROJECT_ID>
export CLAUDE_CODE_OAUTH_TOKEN="$(claude setup-token)"   # personal-use only`}</Code>
            <p>Fill secrets in <code>.env</code> + <code>deploy/terraform/terraform.tfvars</code>, then:</p>
            <Code>{`cp deploy/terraform/terraform.tfvars.example deploy/terraform/terraform.tfvars
./scripts/bootstrap.sh   # enable APIs -> push secrets -> terraform apply -> build/push images -> Turso -> deploy`}</Code>
            <p>Then import the repo into <b>Vercel</b> (root dir = <code>web/</code>) and set these
              <b> server-only</b> env vars:</p>
            <Code>{`API_ORIGIN       = <terraform output api_url>
API_TOKEN        = <same as RESUMAKER_API_TOKEN>
LOGIN_USERNAME   = <your login user>
LOGIN_PASSWORD   = <your login password>
SESSION_SECRET   = <openssl rand -hex 32>`}</Code>
            <Note tone="warn">
              The login gate <b>fails closed</b>: if <code>LOGIN_USERNAME</code>/
              <code>LOGIN_PASSWORD</code>/<code>SESSION_SECRET</code> aren't set on Vercel, the
              deployed app locks everyone out. Set all three.
            </Note>
            <p className="muted">Tear down anytime: <code>cd deploy/terraform && terraform destroy</code>.</p>
          </section>

          <section id="extension">
            <h2 className="doc-h2">Browser extension (optional)</h2>
            <p>Load <code>extension/</code> unpacked (<code>chrome://extensions</code>, then Developer
              mode, then Load unpacked). In Options set the API base URL to your Cloud Run api URL and the
              API token to <code>RESUMAKER_API_TOKEN</code>. It talks to the backend directly, so it's
              independent of the web login.</p>
          </section>

          <section id="troubleshooting">
            <h2 className="doc-h2">Troubleshooting</h2>
            <ul className="doc-list">
              <li><b>Digest never arrives:</b> Resend free tier sends only to your account email.</li>
              <li><b>libsql build fails:</b> build images with <code>--platform linux/amd64</code>.</li>
              <li><b>App locked out:</b> set the three login vars on Vercel.</li>
              <li><b>Server LLM auth:</b> prefer the metered Anthropic API for a hosted instance.</li>
            </ul>
          </section>

          <footer className="doc-foot">
            <Link className="btn" href="/">← Home</Link>
            <Link className="btn btn-primary" href="/login">Login</Link>
          </footer>
        </main>
      </div>
    </div>
  );
}
