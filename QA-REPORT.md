# QA-REPORT.md — invoice-sync (2026-09-15 overnight run, ~00:40 IST)

## Verify (LIVE server, PID 34071, user's own `python3 app.py` on pts/2 since Sep 14)
Note: a second `app.py` instance could not bind (port in use) — all curls below
hit the user's live server on the same dir. Behavior identical: only uncommitted
diff vs HEAD is the `$PORT` line (irrelevant on :8000). Server left running.

- `GET /` → **200** (landing renders)
- `POST /register` → 303, `GET /dashboard` (cookie) → **200**
- `POST /login` → 303, dashboard → **200**
- `POST /clients` (name=TestClient) → 303, `GET /clients` → **200**, page
  contains `TestClient` + delete form `/clients/4/delete`
- `GET /api/chase-due` → **200** `{"due":[]}` (correct — fresh client, nothing overdue)
- PDFs on disk: `pdfs/INV-0001..0003.pdf` (invoice→PDF path proven in prior runs)

## Fixes committed this run
1. `app.py:1283` — uvicorn reads `$PORT` (`int(os.environ.get("PORT","8000"))`).
   Was hardcoded 8000 → Render deploy would crash. **Top ship-blocker, fixed.**
2. `render.yaml` (python env, pip build, `python app.py` start) — new.
3. `Dockerfile` (python:3.12-slim, single process) + `.dockerignore` — new.

## Static PASS (re-audited)
- `TemplateResponse` new signature (`request` first) at all call sites.
- `static/` exists (`.gitkeep`) + `mkdir(exist_ok=True)` guard.
- Razorpay order/verify HMAC (`hmac.new`, `compare_digest`, live + simulated).
- Chase cadence 1/7/14/30 + `reminder_done` dedupe; recurring loop advances
  `next_run` on free-limit skip (no tight loop).
- Auth: PBKDF2 + httpOnly cookie + `samesite=lax`, min-6-char password.

## FAIL / next fixes (ranked)
1. **[verify]** Full invoice→PDF over HTTP on a clean tree (register → client →
   `POST /invoices/new` → `GET /invoices/{id}` → PDF download). PDFs exist on
   disk but the HTTP leg wasn't re-walked this run.
2. **[minor]** `app.py:189` `@app.on_event("startup")` deprecated — migrate to
   `lifespan` before it becomes an error on new Starlette.
3. **[minor]** `rzp_verify` simulated path raises `HTTPException(303)` instead of
   `RedirectResponse("/login")` — logged-out user sees error body, not redirect.
4. **[docs]** README routes section stale (missing `/api/chase-due`,
   `/billing*`, `/clients/{cid}/delete`, chase-pause/paid endpoints).

## GROOT / noshow-guard
**UNREACHED** — `ssh godofnothing@192.168.29.164` → "No route to host"
(laptop asleep/off-LAN); `agy-ssh` binary not present on this host. No agy
invocation this run (shell sufficed; quota preserved, no 429s).

## Repro for next run
```bash
cd ~/prjs/invoice-sync && git log --oneline -3 && git status --short
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/
```
