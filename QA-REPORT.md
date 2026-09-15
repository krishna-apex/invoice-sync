# QA-REPORT.md — invoice-sync (2026-09-15 overnight run, ~02:30 IST)

## Verify — CLEAN TREE (worktree @94428e7, fresh DB, :8001)
`GET /` → **200**. Register → 303, dashboard → **200**, add client → 303.
`POST /invoices/new` → **303** → `GET /invoices/2` → **200** →
`GET /invoices/2/pdf` → **200** `application/pdf`, 2637 bytes, **valid PDF 1.4**.
Prior run's top item (full invoice→PDF over HTTP on clean tree) is now **CLOSED — PASS**.

Note: user's live server (:8000, PID 34071, started Sep 14) still runs pre-HEAD
code — its `POST /invoices/new` returns 200-preview instead of 303-create.
Harmless for now; resolves when the user restarts `python3 app.py`. No action.

False alarm this run: first clean-tree invoice POST returned 500 — root-caused to
my own `| head -20` log pipe (SIGPIPE/BrokenPipe on server prints), NOT app code.
Reran with file logging: 303 + `[PDF] wrote pdfs/INV-0002.pdf`. Lesson: never
pipe a QA server's stdout through `head`.

## Fix committed this run
- `app.py` `rzp_verify` simulated path: logged-out user now gets
  `RedirectResponse("/login", 303)` instead of `HTTPException(303)` error body.
  Verified on throwaway tree: logged-out `POST /billing/razorpay/verify`
  (order_TEST_*) → **303, location: /login**. `py_compile` OK. Live Razorpay
  HMAC path untouched.

## Static PASS (re-audited, unchanged)
- `TemplateResponse` new signature (`request` first) at all call sites.
- `static/` exists + `mkdir(exist_ok=True)` guard; `$PORT` env read; render.yaml + Dockerfile present.
- Chase cadence 1/7/14/30 + `reminder_done` dedupe; recurring loop advances `next_run`.
- Auth: PBKDF2 + httpOnly cookie + samesite=lax, min-6-char password.

## FAIL / next fixes (ranked)
1. **[minor]** `app.py:127` `require_user` still raises `HTTPException(303)` for
   logged-out users on ALL protected routes (same error-body-instead-of-redirect
   class as the rzp fix). Low severity (browsers mostly tolerate it), but one-line
   fix per route or a middleware redirect. Suggested next fix.
2. **[minor]** `app.py:189` `@app.on_event("startup")` deprecated — migrate to
   `lifespan` before it becomes an error on new Starlette.
3. **[docs]** README routes section stale (missing `/api/chase-due`, `/billing*`,
   `/clients/{cid}/delete`, chase-pause/paid endpoints).

## GROOT / noshow-guard
**UNREACHED** — `ssh godofnothing@192.168.29.164` → "No route to host"
(laptop asleep/off-LAN); `agy-ssh` binary not present on this host. No agy
invocation this run (shell sufficed; quota preserved, no 429s).

## Repro for next run
```bash
cd ~/prjs/invoice-sync && git log --oneline -3 && git status --short
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/
```
