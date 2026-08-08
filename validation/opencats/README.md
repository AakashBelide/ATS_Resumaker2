# OpenCATS — real-ATS manual validation (Phase 3.1)

A genuine self-hosted ATS (recruiter UI + candidate search) to eyeball the
"does my resume actually pop up?" test in a real tool. **Fully local, offline, and
NOT part of the per-JD pipeline** — it's a periodic manual confidence check.

> Note: OpenCATS' bundled parser is old and *not* representative of modern
> (Textkernel-class) ATS. Use it for the recruiter **UI + search + ranking feel**;
> use the Affinda oracle (`pocs/ats_sim/affinda.py`) for faithful *parse fidelity*,
> and `pocs/ats_sim` for the automated CI check.

## 1. Start it
```bash
cd validation/opencats
docker compose up -d --build
# open http://localhost:8090/   (index.php redirects to installwizard.php on first launch)
```

## 2. Install wizard (one-time)
Run through the web installer. When it asks for the database, use:

| field | value |
|-------|-------|
| host / server | `db` |
| database name | `cats` |
| user | `cats` |
| password | `cats` |

**Resume Indexing step** — the image ships the extractor binaries so uploaded
resumes are text-indexed (required for content search). Enter these paths and
"Test Configuration" (all green):

| tool | path |
|------|------|
| Antiword (.doc) | `/usr/bin/antiword` |
| PDFToText (.pdf) | `/usr/bin/pdftotext` |
| Html2Text (.html) | `/usr/bin/html2text` |
| UnRTF (.rtf) | `/usr/bin/unrtf` |

(LDAP / SOAP warnings on the System Check are optional — proceed past them.)

Create the admin login when prompted, then log in at `http://localhost:8090/`.

## 3. Generate the candidate files
From the Python env, render our resume + the decoys to PDFs:
```bash
cd resumaker && uv run python ../validation/opencats/make_candidates.py
# -> validation/opencats/candidates/*.pdf  (00_OURS_* + 6 decoys; gitignored)
```

## 4. Run the real test
1. **Add a job order** matching a target JD (e.g. "AI Orchestration Engineer";
   paste the JD text/requirements).
2. **Add candidates** → upload every PDF in `candidates/` (OpenCATS parses each
   into a candidate record — watch how cleanly *our* resume parses vs the wizard).
3. **Recruiter search**: use the candidate keyword/Boolean search with the JD's
   must-haves (e.g. `"multi-agent orchestration" AND RAG AND (LangGraph OR agentic)`).
   Confirm our candidate **surfaces** and ranks at/near the top vs the decoys.
4. (Optional) attach candidates to the job pipeline and compare match ordering.

**Expected** (matches the automated `pocs.ats_sim` result): our resume parses into
clean fields, surfaces for the must-have search, and ranks above all decoys.

## Teardown
```bash
docker compose down          # keep data
docker compose down -v       # wipe the local DB volume too
```
