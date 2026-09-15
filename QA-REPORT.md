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

---
# Night run 2026-09-15 (late, post-02e7e56)

## Verify — HEAD 02e7e56 CLEAN TREE (worktree, fresh DB, :8001) — ALL PASS
Big user-session commit (global money, onboarding, Stripe client-currency,
Row.get fixes) had never been exercised over HTTP — now covered:
`/` → **200** · register → 303 · dashboard → **200** · `POST /clients` → 303 ·
`POST /invoices/new` → 303 · detail → **200** · `/pdf` → **200**
`application/pdf`, 2802 bytes, **valid PDF 1.4** (`file`).
`GET /api/chase-due` → 200 · `/settings` logged-in → 200 ·
logged-out `/dashboard`, `/settings` → **303, location /login**
(global `HTTPException` handler converts 303+location to a real redirect —
**prior item #1 `require_user` CLOSED**).
False alarm: `POST /clients/new` → 422 was my wrong URL; route is `POST /clients`.

## Fix committed this run
- `app.py`: `@app.on_event("startup")` → `lifespan` handler
  (**prior item #2 CLOSED**). Verified on patched throwaway tree: boot clean,
  **zero** `on_event` DeprecationWarnings, recurring loop starts
  (`[APP] InvoiceSync started`), `/` 200, register 303 → dashboard 200.
  User's live :8000 server (PID 80304) untouched, still 200.

## Static audit (HEAD)
- No `.get()` on `sqlite3.Row`: dashboard `enriched` items are `dict(inv)`,
  `u_dict = dict(u)`; remaining `.get(` hits are plain dicts / JSON / env.
  Key-guarded spots (`"paid" in inv.keys()`, `"currency"` fallbacks) intact.
- `TemplateResponse` new signature everywhere; `static/` guard + `$PORT` +
  render.yaml + Dockerfile present.

## FAIL / next fixes (ranked)
1. **[docs]** README routes section stale (missing `/api/chase-due`,
   `/billing*`, `/clients/{cid}/delete`, chase-pause/paid endpoints) —
   now the top item; suggest README refresh next run.
2. **[minor]** Stripe client-currency path never exercised over HTTP
   (needs `STRIPE_SECRET_KEY`); verify redirect/501 behavior without key.
3. **[minor]** Pyright type noise in `app.py` (float-vs-int tax args,
   `UploadFile.strip`) — runtime-harmless, cleanup only.

## GROOT / noshow-guard
**STILL UNREACHED as a target**: ssh to `godofnothing@192.168.29.164` **works**
tonight, but `~/noshow-guard` does not exist on groot, `agy` is not on groot
PATH, and `agy-ssh` is absent on root. Checked `$HOME` dirs — no noshow
scaffold anywhere. Needs user decision: create `~/noshow-guard` on groot
next run, or drop the leg. No agy invocations this run (shell sufficed;
quota preserved, no 429s).

## Repro for next run
```bash
cd ~/prjs/invoice-sync && git log --oneline -3 && git status --short
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/
```
