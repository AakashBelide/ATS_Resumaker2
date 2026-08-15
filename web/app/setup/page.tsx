// Setup docs page (public, `/setup`, RB.3). Anthropic/OpenAI-style guide (Local + Cloud) with a
// sticky side-nav, code blocks, callouts, and reference tables. Mirrors the repo's SETUP.md; the
// runnable scripts (run-local.sh / bootstrap.sh) and the paste-into-a-CLI SETUP_SKILL.md live in the repo.
import Link from "next/link";
import type { ReactNode } from "react";
import ScrollTop from "@/components/ScrollTop";
import DocNav from "@/components/DocNav";

const REPO = "https://github.com/AakashBelide/ATS_Resumaker2";

function Code({ children }: { children: string }) {
  return <pre className="doc-pre"><code>{children}</code></pre>;
}
function Note({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" }) {
  return <div className={`doc-callout ${tone}`}>{children}</div>;
}
const homeIcon = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" width="18" height="18">
    <path d="M3 11l9-8 9 8" /><path d="M5 10v10a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V10" />
  </svg>
);
const ghIcon = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" width="18" height="18"><path d="M9 19c-4 1.5-4-2-5-2.5M15 21v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.3 4.3 0 0 0-.1-3.2s-1-.3-3.5 1.3a12 12 0 0 0-6.2 0C6.9 2.1 5.9 2.4 5.9 2.4a4.3 4.3 0 0 0-.1 3.2A4.6 4.6 0 0 0 4.5 8.8c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21" /></svg>
);

const NAV: [string, string][] = [
  ["overview", "Overview"], ["prereqs", "Prerequisites"], ["profile", "Your profile"],
  ["disclaimers", "Disclaimers"], ["model", "Model selection"], ["local", "A. Local (Docker)"],
  ["cloud", "B. Self-hosting (cloud)"], ["env", "Environment variables"], ["extension", "Browser extension"],
  ["update", "Updating & redeploy"], ["costs", "Costs & free tiers"], ["security", "Security & privacy"],
  ["troubleshooting", "Troubleshooting"], ["faq", "FAQ"],
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
          <Link className="doc-navlink doc-navicon" href="/" title="Home" aria-label="Home">{homeIcon}</Link>
          <a className="doc-navlink doc-navicon" href={REPO} target="_blank" rel="noreferrer" title="View on GitHub" aria-label="GitHub">{ghIcon}</a>
          <Link className="btn btn-sm btn-primary" href="/login">Login</Link>
        </nav>
      </header>

      <div className="doc-layout">
        <DocNav items={NAV} />

        <main className="doc-main">
          <p className="doc-kicker mono">Self-host guide</p>
          <h1 className="doc-h1">Set up ATS Resumaker</h1>
          <p className="doc-lead">
            Run it two ways: <b>Local (Docker)</b> on your machine, or <b>Self-hosting (cloud)</b> on
            Cloud Run + Turso + Vercel within their free tiers. Start local to try it; go cloud when
            you want it always-on (needed for the extension and the email digest).
          </p>
          <Note>
            The full, always-current version of this guide is <code>SETUP.md</code> in the repo, with a
            paste-into-any-CLI <code>SETUP_SKILL.md</code> that can walk you through, and run, these
            steps. The scripts referenced below (<code>scripts/run-local.sh</code>,{" "}
            <code>scripts/bootstrap.sh</code>) live there too.
          </Note>

          <section id="overview">
            <h2 className="doc-h2">Overview</h2>
            <p>The system is a small set of independent pieces that talk over HTTP. The same code runs
              locally and in the cloud, only the seams change (database, job queue, artifact storage).</p>
            <table className="doc-table">
              <thead><tr><th>Piece</th><th>What it is</th><th>Local</th><th>Cloud</th></tr></thead>
              <tbody>
                <tr><td><b>API</b></td><td>FastAPI service, the core of the system</td><td>uvicorn / Docker</td><td>Cloud Run</td></tr>
                <tr><td><b>Worker</b></td><td>runs the pipeline, builds documents</td><td>in-process</td><td>Cloud Run + Cloud Tasks</td></tr>
                <tr><td><b>Scheduler</b></td><td>hourly ingest and the digest cron</td><td>in-process loop</td><td>Cloud Scheduler</td></tr>
                <tr><td><b>Database</b></td><td>tracker, runs, and the canonical profile + preferences</td><td>SQLite file</td><td>Turso (libSQL)</td></tr>
                <tr><td><b>Artifacts</b></td><td>generated resume / cover / screenshots</td><td>local folder</td><td>GCS bucket</td></tr>
                <tr><td><b>Web</b></td><td>Next.js dashboard, BFF proxy + login</td><td>next dev</td><td>Vercel</td></tr>
                <tr><td><b>Extension</b></td><td>MV3 one-click capture</td><td colSpan={2}>talks to the API directly</td></tr>
                <tr><td><b>LLM</b></td><td>tailoring and analysis</td><td colSpan={2}>Claude CLI (your subscription) or the Anthropic API</td></tr>
              </tbody>
            </table>
            <p className="muted">The web app never holds your API token in the browser: it proxies every
              call through a server-side BFF, so the token stays on the server.</p>
          </section>

          <section id="prereqs">
            <h2 className="doc-h2">Prerequisites</h2>
            <table className="doc-table">
              <thead><tr><th>Tool</th><th>For</th></tr></thead>
              <tbody>
                <tr><td><b>git</b></td><td>cloning the repo</td></tr>
                <tr><td><b>Docker + Compose</b></td><td>local run (required)</td></tr>
                <tr><td><b>uv</b></td><td>Python runtime (CLI / dev)</td></tr>
                <tr><td><b>Node 20+</b></td><td>the web dashboard</td></tr>
                <tr><td><b>Claude CLI</b></td><td>the default LLM engine (subscription)</td></tr>
                <tr><td><b>gcloud, Terraform 1.6+, Turso CLI</b></td><td><i>cloud only</i></td></tr>
              </tbody>
            </table>
          </section>

          <section id="profile">
            <h2 className="doc-h2">Your profile is the source of truth</h2>
            <p>Everything generated traces to your profile, your real employers, titles, metrics, and
              skills. It lives in the app <b>database</b> (local SQLite or cloud Turso); a{" "}
              <code>data/profile/profile.json</code> file is the initial <b>seed</b>, migrated in on
              first read. <b>Create it before onboarding or generating.</b> Easiest is the in-app{" "}
              <b>Assistant</b> page, which onboards a profile three ways, all writing to the canonical store:</p>
            <ul className="doc-list">
              <li><b>First-time template</b> — download the schema, fill it in, seed it
                deterministically. Lossless: keeps hand-curated fields (equivalence map, target
                archetypes) an AI parse can&apos;t infer.</li>
              <li><b>AI parse</b> — upload a resume <b>PDF/DOCX</b> (or paste text); it extracts a
                profile with zero invention that you <b>review before applying</b> (first-time gated,
                so it won&apos;t overwrite an existing profile without confirming).</li>
              <li><b>Enhance chat</b> — probe-and-confirm to fill gaps and add metrics; every write is
                grounded in your own words and reversible with <code>/undo</code>.</li>
            </ul>
            <p>Or hand-write it from the schema. The same onboarding works on a fresh cloud deploy (the
              DB starts empty). <code>data/</code> is gitignored PII, it never leaves your machine or
              your bucket.</p>
          </section>

          <section id="disclaimers">
            <h2 className="doc-h2">Disclaimers</h2>
            <ul className="doc-list">
              <li><b>Cost:</b> the cloud path is designed to fit free tiers, but the LLM is not free.
                Hosting is roughly <code>$0/mo</code> on the free tiers below; your <b>Claude
                subscription or Anthropic API usage is separate and billed by Anthropic.</b> Attach
                billing to GCP and set a <b>$1 budget alert</b> anyway.</li>
              <li><b>Claude CLI OAuth is personal-use only.</b> <code>claude setup-token</code> is for
                <i> your</i> subscription; running it on a shared / hosted server may breach ToS and hit
                rate limits. For a real hosted instance use the metered Anthropic API
                (<code>RESUMAKER_DEFAULT_PROVIDER=anthropic</code> + <code>ANTHROPIC_API_KEY</code>).</li>
              <li><b>Human-in-the-loop:</b> it advises and drafts; it never auto-applies.</li>
            </ul>
          </section>

          <section id="model">
            <h2 className="doc-h2">Choosing the Claude model</h2>
            <p>The model tier is env-selectable, so pick per your subscription and usage:</p>
            <Code>{`RESUMAKER_MODEL_FAST=claude-haiku-4-5        # cheap extraction
RESUMAKER_MODEL_STANDARD=claude-sonnet-4-5   # analysis / match
RESUMAKER_MODEL_QUALITY=claude-opus-4-8      # tailoring`}</Code>
            <p className="muted">On a lower-usage plan, a <b>budget preset</b> (Sonnet for standard and
              quality, Haiku for fast) keeps quality high at lower cost.</p>
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
            <p className="muted">Prefer the CLI without Docker? <code>uv sync --all-extras</code> then{" "}
              <code>uv run python -m apps.cli serve</code> (needs LibreOffice + a Chromium for capture).</p>
          </section>

          <section id="cloud">
            <h2 className="doc-h2">B. Self-hosting (cloud)</h2>
            <p><b>Do the account setup in this order:</b></p>
            <ol className="doc-list">
              <li><b>Google Cloud</b>, create a project, <b>enable billing</b>, set a $1 budget alert,
                region <code>us-central1</code> (keeps GCS free).</li>
              <li><b>Turso</b>, create a DB; grab its URL (<code>libsql://...</code>) and auth token.</li>
              <li><b>Resend</b>, sign up <b>with the SAME email you want the digest delivered to</b>
                {" "}(the free tier only sends to your own verified address). Create an API key.</li>
              <li><b>Vercel</b>, sign up (GitHub login); you deploy <code>web/</code> here.</li>
              <li><b>GitHub</b>, fork the repo; Actions deploy on push to <code>main</code>.</li>
            </ol>
            <Note tone="warn">
              The <b>Resend same-email</b> detail is easy to miss: on the free tier the digest silently
              will not arrive unless the recipient is your Resend account email.
            </Note>
            <p>Interactive auth (cannot be scripted):</p>
            <Code>{`gcloud auth login
gcloud auth application-default login
gcloud config set project <YOUR_PROJECT_ID>
export CLAUDE_CODE_OAUTH_TOKEN="$(claude setup-token)"   # personal-use only`}</Code>
            <p>Fill secrets in <code>.env</code> and <code>deploy/terraform/terraform.tfvars</code>, then:</p>
            <Code>{`cp deploy/terraform/terraform.tfvars.example deploy/terraform/terraform.tfvars
./scripts/bootstrap.sh   # enable APIs -> push secrets -> terraform apply -> build/push images -> Turso -> deploy`}</Code>
            <p>Then import the repo into <b>Vercel</b> (root dir = <code>web/</code>) and set the
              server-only env vars from the next section.</p>
            <p className="muted">Tear down anytime: <code>cd deploy/terraform && terraform destroy</code>.</p>
          </section>

          <section id="env">
            <h2 className="doc-h2">Environment variables</h2>
            <p><b>Backend</b> (<code>.env</code>, and pushed to Secret Manager on the cloud path):</p>
            <table className="doc-table">
              <thead><tr><th>Variable</th><th>Purpose</th></tr></thead>
              <tbody>
                <tr><td><code>RESUMAKER_API_TOKEN</code></td><td>bearer token the web app and extension use to call the API</td></tr>
                <tr><td><code>RESUMAKER_DEFAULT_PROVIDER</code></td><td><code>claude-cli</code> (default) or <code>anthropic</code></td></tr>
                <tr><td><code>ANTHROPIC_API_KEY</code></td><td>required when the provider is <code>anthropic</code></td></tr>
                <tr><td><code>CLAUDE_CODE_OAUTH_TOKEN</code></td><td>from <code>claude setup-token</code>, for the Claude CLI provider</td></tr>
                <tr><td><code>RESUMAKER_MODEL_FAST / STANDARD / QUALITY</code></td><td>model tier per pipeline stage</td></tr>
                <tr><td><code>TURSO_DATABASE_URL / TURSO_AUTH_TOKEN</code></td><td>cloud database (omit to use local SQLite)</td></tr>
                <tr><td><code>RESEND_API_KEY</code></td><td>email digest sender</td></tr>
                <tr><td><code>NOTIFY_TO / NOTIFY_FROM</code></td><td>digest recipient and from address (same on Resend free tier)</td></tr>
              </tbody>
            </table>
            <p><b>Web app</b> (Vercel, all server-only, never <code>NEXT_PUBLIC_*</code>):</p>
            <table className="doc-table">
              <thead><tr><th>Variable</th><th>Purpose</th></tr></thead>
              <tbody>
                <tr><td><code>API_ORIGIN</code></td><td>the API URL (<code>terraform output api_url</code>)</td></tr>
                <tr><td><code>API_TOKEN</code></td><td>same value as <code>RESUMAKER_API_TOKEN</code></td></tr>
                <tr><td><code>LOGIN_USERNAME / LOGIN_PASSWORD</code></td><td>the static login credentials</td></tr>
                <tr><td><code>SESSION_SECRET</code></td><td>HMAC key for the session cookie (<code>openssl rand -hex 32</code>)</td></tr>
              </tbody>
            </table>
            <Note tone="warn">
              The login gate <b>fails closed</b>: if <code>LOGIN_USERNAME</code> /{" "}
              <code>LOGIN_PASSWORD</code> / <code>SESSION_SECRET</code> are not set on Vercel, the
              deployed app locks everyone out. Set all three.
            </Note>
          </section>

          <section id="extension">
            <h2 className="doc-h2">Browser extension (optional)</h2>
            <p>Load <code>extension/</code> unpacked (<code>chrome://extensions</code>, then Developer
              mode, then Load unpacked). In Options set the API base URL to your API URL and the API
              token to <code>RESUMAKER_API_TOKEN</code>. It talks to the backend directly, so it is
              independent of the web login. It captures the posting text plus a full-page screenshot.</p>
          </section>

          <section id="update">
            <h2 className="doc-h2">Updating and redeploying</h2>
            <ul className="doc-list">
              <li><b>Web:</b> Vercel auto-deploys on every push to <code>main</code>.</li>
              <li><b>Backend:</b> pushing to <code>main</code> triggers the GitHub Actions workflow,
                which builds the <code>amd64</code> images, pushes them to Artifact Registry, and rolls
                the Cloud Run services. It authenticates with <b>Workload Identity Federation</b>, so
                there are no long-lived cloud keys in GitHub.</li>
              <li><b>Infra changes:</b> edit <code>deploy/terraform</code> and re-run{" "}
                <code>terraform apply</code> (or <code>./scripts/bootstrap.sh</code>).</li>
              <li><b>Config-only changes:</b> update the value in Secret Manager and redeploy the
                affected service.</li>
            </ul>
            <Note>
              The GitHub Actions workflow reads the project / region / identity from repo{" "}
              <b>Variables</b> (<code>GCP_PROJECT</code>, <code>GCP_WIF_PROVIDER</code>,{" "}
              <code>GCP_DEPLOY_SA</code>), not from anything committed, so your fork stays generic.
            </Note>
          </section>

          <section id="costs">
            <h2 className="doc-h2">Costs and free tiers</h2>
            <p>Single-user usage sits well inside every free tier. Hosting is effectively{" "}
              <code>$0/mo</code>; the only real cost is the LLM, which is your existing Claude
              subscription or metered Anthropic API usage, billed separately by Anthropic.</p>
            <table className="doc-table">
              <thead><tr><th>Service</th><th>Free tier</th></tr></thead>
              <tbody>
                <tr><td>Cloud Run</td><td>240k vCPU-sec + 450k GiB-sec / month</td></tr>
                <tr><td>Cloud Storage</td><td>5 GB (us-central1)</td></tr>
                <tr><td>Turso</td><td>3 GB / billions of row reads</td></tr>
                <tr><td>Cloud Scheduler</td><td>3 free jobs</td></tr>
                <tr><td>GitHub Actions</td><td>2000 min / month</td></tr>
                <tr><td>Vercel</td><td>Hobby plan</td></tr>
              </tbody>
            </table>
          </section>

          <section id="security">
            <h2 className="doc-h2">Security and privacy</h2>
            <ul className="doc-list">
              <li><b>Your data stays yours.</b> <code>data/</code> (profile PII), <code>.env</code>, and
                Terraform state are gitignored; nothing personal is committed.</li>
              <li><b>The token never reaches the browser.</b> The web app proxies API calls through a
                server-side BFF; the extension talks to the API directly with its own token.</li>
              <li><b>Login fails closed</b> and the session is an HMAC-signed httpOnly cookie, valid ~30
                days, with no client-side bypass.</li>
              <li><b>Keyless CI:</b> deploys use Workload Identity Federation, so there is no
                long-lived service-account key stored anywhere.</li>
              <li><b>Human-in-the-loop:</b> the system advises and drafts. It never auto-applies.</li>
            </ul>
          </section>

          <section id="troubleshooting">
            <h2 className="doc-h2">Troubleshooting</h2>
            <ul className="doc-list">
              <li><b>Digest never arrives:</b> Resend free tier sends only to your account email.</li>
              <li><b>libsql build fails:</b> build images with <code>--platform linux/amd64</code>.</li>
              <li><b>App locked out:</b> set the three login vars on Vercel.</li>
              <li><b>Server LLM auth:</b> prefer the metered Anthropic API for a hosted instance.</li>
              <li><b>Capture screenshot is only the viewport:</b> the extension stretches the layout
                viewport before capturing; keep DevTools closed for the full-page path.</li>
            </ul>
          </section>

          <section id="faq">
            <h2 className="doc-h2">FAQ</h2>
            <p><b>Do I have to use the cloud?</b> No. Local (Docker) is fully functional; go cloud only
              when you want it always-on for the extension and the digest.</p>
            <p><b>Can I use my own API key instead of a subscription?</b> Yes, set{" "}
              <code>RESUMAKER_DEFAULT_PROVIDER=anthropic</code> and <code>ANTHROPIC_API_KEY</code>.</p>
            <p><b>Does it apply to jobs for me?</b> No. It surfaces roles, scores fit, and drafts
              grounded documents. You review and apply.</p>
            <p><b>Where do generated files go?</b> A local folder on the local path, or your GCS bucket
              in the cloud; the dashboard downloads them for you.</p>
          </section>

          <footer className="doc-foot">
            <Link className="btn" href="/">{homeIcon}Home</Link>
            <a className="btn" href={REPO} target="_blank" rel="noreferrer">{ghIcon}View on GitHub</a>
          </footer>
        </main>
      </div>
      <ScrollTop />
    </div>
  );
}
