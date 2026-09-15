"""SQLite data layer for InvoiceSync. Pure stdlib + sqlite3."""
import sqlite3
import os
import hashlib
import secrets
import json
import re
from datetime import datetime, timezone, timedelta

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "invoicesync.db"))

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'free',
            stripe_customer_id TEXT,
            api_token TEXT,
            next_invoice_seq INTEGER DEFAULT 1,
            invoice_prefix TEXT DEFAULT '2026-',
            base_currency TEXT DEFAULT 'USD',
            locale TEXT DEFAULT 'en-US',
            onboarding_completed INTEGER DEFAULT 0,
            default_terms TEXT DEFAULT 'Net 30',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            email TEXT,
            currency TEXT NOT NULL DEFAULT 'USD',
            rate REAL NOT NULL DEFAULT 0,
            custom_fields_json TEXT,
            tax_percent REAL DEFAULT 0,
            locale TEXT DEFAULT 'en-US',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS time_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            client_id INTEGER,
            description TEXT,
            seconds INTEGER NOT NULL,
            date TEXT NOT NULL,
            source TEXT NOT NULL,
            billed INTEGER DEFAULT 0,
            invoice_id INTEGER,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            client_id INTEGER NOT NULL,
            number TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            amount REAL NOT NULL,
            amount_minor INTEGER,
            currency TEXT DEFAULT 'USD',
            status TEXT NOT NULL DEFAULT 'draft',
            pdf_path TEXT,
            terms TEXT DEFAULT 'Due on receipt',
            notes TEXT,
            due_date TEXT,
            paid INTEGER DEFAULT 0,
            chase_paused INTEGER DEFAULT 0,
            line_items_json TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, number)
        );
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER PRIMARY KEY,
            stripe_sub_id TEXT,
            plan TEXT,
            status TEXT,
            renews_at TEXT
        );
        CREATE TABLE IF NOT EXISTS recurring_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            client_id INTEGER NOT NULL,
            amount REAL,
            custom_fields_json TEXT,
            period_days INTEGER NOT NULL DEFAULT 30,
            last_run TEXT,
            next_run TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            invoice_id INTEGER NOT NULL,
            day INTEGER NOT NULL,
            sent_at TEXT NOT NULL,
            UNIQUE(invoice_id, day)
        );
        CREATE TABLE IF NOT EXISTS password_resets (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_time_entries_user_date ON time_entries(user_id, date);
        CREATE INDEX IF NOT EXISTS idx_invoices_user_created ON invoices(user_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_clients_user ON clients(user_id);
    """)
    conn.commit()
    conn.close()

    # migrate: check if invoices table has old global unique on number (number TEXT UNIQUE)
    try:
        conn = get_conn()
        inv_sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='invoices'").fetchone()
        if inv_sql and ("number TEXT UNIQUE" in inv_sql["sql"]):
            cols = [c["name"] for c in conn.execute("PRAGMA table_info(invoices)").fetchall()]
            conn.execute("""
                CREATE TABLE invoices_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    client_id INTEGER NOT NULL,
                    number TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    amount REAL NOT NULL,
                    amount_minor INTEGER,
                    currency TEXT DEFAULT 'USD',
                    status TEXT NOT NULL DEFAULT 'draft',
                    pdf_path TEXT,
                    terms TEXT DEFAULT 'Due on receipt',
                    notes TEXT,
                    due_date TEXT,
                    paid INTEGER DEFAULT 0,
                    chase_paused INTEGER DEFAULT 0,
                    line_items_json TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, number)
                )
            """)
            common = [c for c in cols if c in [
                "id", "user_id", "client_id", "number", "period_start", "period_end", "amount",
                "status", "pdf_path", "terms", "notes", "due_date", "paid", "chase_paused",
                "currency", "amount_minor", "line_items_json", "created_at"
            ]]
            cols_str = ", ".join(common)
            conn.execute(f"INSERT INTO invoices_v2 ({cols_str}) SELECT {cols_str} FROM invoices")
            conn.execute("DROP TABLE invoices")
            conn.execute("ALTER TABLE invoices_v2 RENAME TO invoices")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_invoices_user_created ON invoices(user_id, created_at)")
            conn.commit()
            print("[DB] migrated invoices table to UNIQUE(user_id, number)")
        conn.close()
    except Exception as e:
        print("[DB-MIGRATE-INV-ERR]", e)

    # migrate: add api_token column if missing for old dbs
    for _col in (
        "api_token TEXT",
        "next_invoice_seq INTEGER DEFAULT 1",
        "invoice_prefix TEXT DEFAULT '2026-'",
        "base_currency TEXT DEFAULT 'USD'",
        "locale TEXT DEFAULT 'en-US'",
        "onboarding_completed INTEGER DEFAULT 0",
        "default_terms TEXT DEFAULT 'Net 30'",
        "business_name TEXT",
        "business_address TEXT",
        "business_city TEXT",
        "business_country TEXT",
        "business_tax_id TEXT",
        "logo_path TEXT",
        "timezone TEXT DEFAULT 'America/New_York'",
        "upi_id TEXT",
        "payment_link TEXT",
        "dismissed_branding_prompt INTEGER DEFAULT 0",
    ):
        try:
            conn = get_conn()
            conn.execute(f"ALTER TABLE users ADD COLUMN {_col}")
            conn.commit()
            conn.close()
        except Exception:
            pass

    # migrate: chase columns, currency, line_items_json on invoices
    for _col in (
        "due_date TEXT", "paid INTEGER DEFAULT 0", "chase_paused INTEGER DEFAULT 0",
        "terms TEXT DEFAULT 'Due on receipt'", "notes TEXT",
        "currency TEXT DEFAULT 'USD'", "amount_minor INTEGER", "line_items_json TEXT"
    ):
        try:
            conn = get_conn()
            conn.execute(f"ALTER TABLE invoices ADD COLUMN {_col}")
            conn.commit()
            conn.close()
        except Exception:
            pass

    # migrate: tax_percent, locale on clients
    for _col in ("tax_percent REAL DEFAULT 0", "locale TEXT DEFAULT 'en-US'"):
        try:
            conn = get_conn()
            conn.execute(f"ALTER TABLE clients ADD COLUMN {_col}")
            conn.commit()
            conn.close()
        except Exception:
            pass

    # migrate: billed, invoice_id on time_entries
    for _col in ("billed INTEGER DEFAULT 0", "invoice_id INTEGER"):
        try:
            conn = get_conn()
            conn.execute(f"ALTER TABLE time_entries ADD COLUMN {_col}")
            conn.commit()
            conn.close()
        except Exception:
            pass

    print("[DB] initialized at", DB_PATH)

# ---------- auth ----------
def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 100_000)
    return salt + ":" + dk.hex()

def verify_password(pw: str, stored: str) -> bool:
    try:
        salt, dk = stored.split(":")
        expected = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 100_000).hex()
        return secrets.compare_digest(expected, dk)
    except Exception:
        return False

def create_user(email: str, pw: str) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (email, password_hash, plan, created_at) VALUES (?,?,?,?)",
        (email.lower().strip(), hash_password(pw), "free", datetime.now(timezone.utc).isoformat()),
    )
    uid = cur.lastrowid
    conn.commit()
    conn.close()
    print(f"[AUTH] created user {email} id={uid}")
    return uid

def get_user_by_email(email: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE email=?", (email.lower().strip(),)).fetchone()
    conn.close()
    return row

def get_user_by_id(uid: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return row

def get_user_by_token(token: str):
    conn = get_conn()
    s = conn.execute("SELECT user_id FROM sessions WHERE token=?", (token,)).fetchone()
    if not s:
        conn.close()
        return None
    u = conn.execute("SELECT * FROM users WHERE id=?", (s["user_id"],)).fetchone()
    conn.close()
    return u

def create_session(user_id: int) -> str:
    token = secrets.token_hex(32)
    conn = get_conn()
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at) VALUES (?,?,?)",
        (token, user_id, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    return token

def destroy_session(token: str):
    conn = get_conn()
    conn.execute("DELETE FROM sessions WHERE token=?", (token,))
    conn.commit()
    conn.close()

def set_plan(user_id: int, plan: str):
    conn = get_conn()
    conn.execute("UPDATE users SET plan=? WHERE id=?", (plan, user_id))
    conn.commit()
    conn.close()
    print(f"[BILLING] user {user_id} plan -> {plan}")

def set_stripe_customer(user_id: int, customer_id: str):
    conn = get_conn()
    conn.execute("UPDATE users SET stripe_customer_id=? WHERE id=?", (customer_id, user_id))
    conn.commit()
    conn.close()

def set_api_token(user_id: int, token: str):
    conn = get_conn()
    conn.execute("UPDATE users SET api_token=? WHERE id=?", (token, user_id))
    conn.commit()
    conn.close()

def update_business_profile(user_id: int, business_name: str, business_address: str, business_city: str, business_country: str, business_tax_id: str, logo_path: str = None):
    conn = get_conn()
    if logo_path is not None:
        conn.execute(
            "UPDATE users SET business_name=?, business_address=?, business_city=?, business_country=?, business_tax_id=?, logo_path=? WHERE id=?",
            (business_name, business_address, business_city, business_country, business_tax_id, logo_path, user_id)
        )
    else:
        conn.execute(
            "UPDATE users SET business_name=?, business_address=?, business_city=?, business_country=?, business_tax_id=? WHERE id=?",
            (business_name, business_address, business_city, business_country, business_tax_id, user_id)
        )
    conn.commit()
    conn.close()
    print(f"[PROFILE] updated business profile user={user_id}")

def update_user_settings(user_id: int, timezone: str = None, upi_id: str = None, payment_link: str = None, business_name: str = None, business_address: str = None, business_city: str = None, business_country: str = None, business_tax_id: str = None, logo_path: str = None):
    conn = get_conn()
    u = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not u:
        conn.close()
        return
    u_dict = dict(u)
    tz = timezone if timezone is not None else u_dict.get("timezone", "Asia/Kolkata")
    upi = upi_id if upi_id is not None else u_dict.get("upi_id", "")
    plink = payment_link if payment_link is not None else u_dict.get("payment_link", "")
    bname = business_name if business_name is not None else u_dict.get("business_name", "")
    baddr = business_address if business_address is not None else u_dict.get("business_address", "")
    bcity = business_city if business_city is not None else u_dict.get("business_city", "")
    bcountry = business_country if business_country is not None else u_dict.get("business_country", "")
    btax = business_tax_id if business_tax_id is not None else u_dict.get("business_tax_id", "")
    logo = logo_path if logo_path is not None else u_dict.get("logo_path", "")
    conn.execute(
        "UPDATE users SET timezone=?, upi_id=?, payment_link=?, business_name=?, business_address=?, business_city=?, business_country=?, business_tax_id=?, logo_path=? WHERE id=?",
        (tz, upi, plink, bname, baddr, bcity, bcountry, btax, logo, user_id)
    )
    conn.commit()
    conn.close()
    print(f"[SETTINGS] updated settings user={user_id}")

def dismiss_branding_prompt(user_id: int):
    conn = get_conn()
    conn.execute("UPDATE users SET dismissed_branding_prompt=1 WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    print(f"[ONBOARDING] dismissed branding prompt user={user_id}")


# ---------- clients ----------
def add_client(user_id, name, email, currency, rate, custom_fields_json, tax_percent=0, locale="en-US"):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    cur = conn.cursor()
    try:
        taxp = float(tax_percent or 0)
    except Exception:
        taxp = 0
    cur.execute(
        "INSERT INTO clients (user_id, name, email, currency, rate, custom_fields_json, tax_percent, locale, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (user_id, name, email, currency or "USD", float(rate or 0), custom_fields_json, taxp, locale or "en-US", now),
    )
    cid = cur.lastrowid
    conn.commit()
    conn.close()
    print(f"[CLIENT] added {name} id={cid} user={user_id}")
    return cid

def list_clients(user_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM clients WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()
    conn.close()
    return rows

def get_client(cid, user_id=None):
    conn = get_conn()
    if user_id:
        row = conn.execute("SELECT * FROM clients WHERE id=? AND user_id=?", (cid, user_id)).fetchone()
    else:
        row = conn.execute("SELECT * FROM clients WHERE id=?", (cid,)).fetchone()
    conn.close()
    return row

def update_client(cid, user_id, name, email, currency, rate, custom_fields_json, tax_percent=None, locale="en-US"):
    conn = get_conn()
    if tax_percent is None:
        conn.execute(
            "UPDATE clients SET name=?, email=?, currency=?, rate=?, custom_fields_json=?, locale=? WHERE id=? AND user_id=?",
            (name, email, currency or "USD", float(rate or 0), custom_fields_json, locale or "en-US", cid, user_id),
        )
    else:
        try:
            taxp = float(tax_percent or 0)
        except Exception:
            taxp = 0
        conn.execute(
            "UPDATE clients SET name=?, email=?, currency=?, rate=?, custom_fields_json=?, tax_percent=?, locale=? WHERE id=? AND user_id=?",
            (name, email, currency or "USD", float(rate or 0), custom_fields_json, taxp, locale or "en-US", cid, user_id),
        )
    conn.commit()
    conn.close()

def delete_client(cid, user_id):
    conn = get_conn()
    conn.execute("DELETE FROM clients WHERE id=? AND user_id=?", (cid, user_id))
    conn.commit()
    conn.close()

# ---------- time_entries ----------
def add_time_entry(user_id, client_id, description, seconds, date, source="manual"):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO time_entries (user_id, client_id, description, seconds, date, source, billed, created_at) VALUES (?,?,?,?,?,?,0,?)",
        (user_id, client_id, description, int(seconds), date, source, now),
    )
    conn.commit()
    conn.close()

def list_time_entries(user_id, client_id=None, start=None, end=None):
    conn = get_conn()
    q = "SELECT * FROM time_entries WHERE user_id=?"
    params = [user_id]
    if client_id:
        q += " AND client_id=?"
        params.append(client_id)
    if start:
        q += " AND date >= ?"
        params.append(start)
    if end:
        q += " AND date <= ?"
        params.append(end)
    q += " ORDER BY date ASC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return rows

def list_unbilled_time_entries(user_id, client_id=None, start=None, end=None):
    conn = get_conn()
    q = "SELECT * FROM time_entries WHERE user_id=? AND COALESCE(billed,0)=0"
    params = [user_id]
    if client_id:
        q += " AND client_id=?"
        params.append(client_id)
    if start:
        q += " AND date >= ?"
        params.append(start)
    if end:
        q += " AND date <= ?"
        params.append(end)
    q += " ORDER BY date ASC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return rows

def mark_time_entries_billed(entry_ids, invoice_id):
    if not entry_ids:
        return
    conn = get_conn()
    qmarks = ",".join("?" for _ in entry_ids)
    conn.execute(f"UPDATE time_entries SET billed=1, invoice_id=? WHERE id IN ({qmarks})", [invoice_id] + list(entry_ids))
    conn.commit()
    conn.close()

def count_time_entries(user_id):
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) c FROM time_entries WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row["c"]

# ---------- invoices ----------
def count_invoices_this_month(user_id):
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) c FROM invoices WHERE user_id=? AND created_at >= ?", (user_id, start)).fetchone()
    conn.close()
    return row["c"]

def next_invoice_number(user_id):
    conn = get_conn()
    u = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    u_dict = dict(u) if u else {}
    current_year = datetime.now(timezone.utc).year
    default_prefix = f"{current_year}-"
    prefix = u_dict.get("invoice_prefix") or default_prefix
    seq = u_dict.get("next_invoice_seq")

    if not seq or seq < 1:
        # FreshBooks pattern: numbering from per-user MAX invoice id (never reuse deleted numbers)
        rows = conn.execute("SELECT id, number FROM invoices WHERE user_id=? ORDER BY id ASC", (user_id,)).fetchall()
        max_seq = 0
        max_id = 0
        for r in rows:
            max_id = max(max_id, r["id"])
            m = re.search(r"(\d+)$", r["number"])
            if m:
                max_seq = max(max_seq, int(m.group(1)))
        seq = max(max_seq, max_id) + 1
        conn.execute("UPDATE users SET next_invoice_seq=?, invoice_prefix=? WHERE id=?", (seq, prefix, user_id))
        conn.commit()

    conn.close()
    return f"{prefix}{seq:04d}"

def reseed_invoice_sequence(user_id, number):
    m = re.search(r"^(.*?)(0*(\d+))$", str(number).strip())
    if m:
        prefix = m.group(1) or f"{datetime.now(timezone.utc).year}-"
        seq = int(m.group(3))
        next_seq = seq + 1
        conn = get_conn()
        conn.execute("UPDATE users SET next_invoice_seq=?, invoice_prefix=? WHERE id=?", (next_seq, prefix, user_id))
        conn.commit()
        conn.close()

def get_invoice_by_number(user_id, number):
    conn = get_conn()
    row = conn.execute("SELECT * FROM invoices WHERE user_id=? AND number=?", (user_id, str(number).strip())).fetchone()
    conn.close()
    return row

def create_invoice(user_id, client_id, period_start, period_end, amount, status="draft", pdf_path=None, terms="Due on receipt", notes="", due_date=None, number=None, currency="USD", line_items_json=None):
    from pdf import to_minor_units
    num = str(number).strip() if number and str(number).strip() else next_invoice_number(user_id)
    curr = (currency or "USD").upper().strip()
    amt = float(amount or 0)
    amt_minor = to_minor_units(amt, curr)
    now = datetime.now(timezone.utc).isoformat()

    conn = get_conn()
    # friendly duplicate check
    existing = conn.execute("SELECT id FROM invoices WHERE user_id=? AND number=?", (user_id, num)).fetchone()
    if existing:
        conn.close()
        raise ValueError(f"Invoice number '{num}' is already used.")

    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT INTO invoices (
                user_id, client_id, number, period_start, period_end, amount, amount_minor,
                currency, status, pdf_path, terms, notes, due_date, line_items_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                user_id, client_id, num, period_start, period_end, amt, amt_minor,
                curr, status, pdf_path, terms or "Due on receipt", notes or "", due_date,
                line_items_json, now
            ),
        )
        iid = cur.lastrowid
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError:
        conn.close()
        raise ValueError(f"Invoice number '{num}' is already used.")

    # Re-seed sequence after manual override or auto number (Invoicely pattern)
    reseed_invoice_sequence(user_id, num)

    print(f"[INVOICE] created {num} amount={amt} {curr} user={user_id} status={status}")
    return iid, num

def approve_invoice(iid, user_id):
    conn = get_conn()
    inv = conn.execute("SELECT * FROM invoices WHERE id=? AND user_id=?", (iid, user_id)).fetchone()
    if not inv:
        conn.close()
        return False
    inv_dict = dict(inv)
    if inv_dict.get("status") == "draft":
        due_date = inv_dict.get("due_date")
        if not due_date:
            terms = inv_dict.get("terms") or "Due on receipt"
            days = 0
            if "14" in terms or "15" in terms:
                days = 14
            elif "30" in terms:
                days = 30
            elif "60" in terms:
                days = 60
            due_date = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()[:10]
        conn.execute("UPDATE invoices SET status='approved', due_date=? WHERE id=? AND user_id=?", (due_date, iid, user_id))
        conn.commit()
    conn.close()
    return True

def update_invoice_notes_and_terms(iid, user_id, terms=None, notes=None):
    conn = get_conn()
    if terms is not None and notes is not None:
        conn.execute("UPDATE invoices SET terms=?, notes=? WHERE id=? AND user_id=?", (terms, notes, iid, user_id))
    elif terms is not None:
        conn.execute("UPDATE invoices SET terms=? WHERE id=? AND user_id=?", (terms, iid, user_id))
    elif notes is not None:
        conn.execute("UPDATE invoices SET notes=? WHERE id=? AND user_id=?", (notes, iid, user_id))
    conn.commit()
    conn.close()

def list_invoices(user_id, limit=20):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM invoices WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (user_id, limit)).fetchall()
    conn.close()
    return rows

def get_invoice(iid, user_id=None):
    conn = get_conn()
    if user_id:
        row = conn.execute("SELECT * FROM invoices WHERE id=? AND user_id=?", (iid, user_id)).fetchone()
    else:
        row = conn.execute("SELECT * FROM invoices WHERE id=?", (iid,)).fetchone()
    conn.close()
    return row

def set_invoice_pdf(iid, pdf_path):
    conn = get_conn()
    conn.execute("UPDATE invoices SET pdf_path=? WHERE id=?", (pdf_path, iid))
    conn.commit()
    conn.close()

def set_invoice_status(iid, status, user_id=None):
    conn = get_conn()
    if user_id:
        conn.execute("UPDATE invoices SET status=? WHERE id=? AND user_id=?", (status, iid, user_id))
    else:
        conn.execute("UPDATE invoices SET status=? WHERE id=?", (status, iid))
    conn.commit()
    conn.close()

# ---------- password resets ----------
def create_password_reset(user_id):
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(hours=1)).isoformat()
    conn = get_conn()
    conn.execute(
        "INSERT INTO password_resets (token, user_id, expires_at, used, created_at) VALUES (?,?,?,?,?)",
        (token, user_id, expires_at, 0, now.isoformat()),
    )
    conn.commit()
    conn.close()
    return token

def get_valid_password_reset(token):
    conn = get_conn()
    row = conn.execute("SELECT * FROM password_resets WHERE token=? AND used=0", (token,)).fetchone()
    conn.close()
    if not row:
        return None
    r_dict = dict(row)
    now_iso = datetime.now(timezone.utc).isoformat()
    if now_iso > r_dict.get("expires_at", ""):
        return None
    return r_dict

def reset_password(token, new_password):
    rec = get_valid_password_reset(token)
    if not rec:
        return None
    uid = rec["user_id"]
    conn = get_conn()
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(new_password), uid))
    conn.execute("UPDATE password_resets SET used=1 WHERE token=?", (token,))
    conn.commit()
    conn.close()
    return uid

# ---------- onboarding ----------
def complete_onboarding(user_id, business_name=None, country=None, base_currency="USD", logo_path=None, terms="Net 30"):
    conn = get_conn()
    conn.execute(
        "UPDATE users SET business_name=COALESCE(?, business_name), business_country=COALESCE(?, business_country), base_currency=COALESCE(?, base_currency), logo_path=COALESCE(?, logo_path), default_terms=COALESCE(?, default_terms), onboarding_completed=1 WHERE id=?",
        (business_name or None, country or None, base_currency or "USD", logo_path or None, terms or "Net 30", user_id),
    )
    conn.commit()
    conn.close()

# ---------- subscriptions ----------
def upsert_subscription(user_id, stripe_sub_id, plan, status, renews_at):
    conn = get_conn()
    conn.execute(
        "INSERT INTO subscriptions (user_id, stripe_sub_id, plan, status, renews_at) VALUES (?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET stripe_sub_id=?, plan=?, status=?, renews_at=?",
        (user_id, stripe_sub_id, plan, status, renews_at, stripe_sub_id, plan, status, renews_at),
    )
    conn.commit()
    conn.close()

def get_subscription(user_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM subscriptions WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row

# ---------- recurring ----------
def add_recurring_template(user_id, client_id, period_days=30, custom_fields_json=None):
    now = datetime.now(timezone.utc)
    next_run = (now + timezone.utc.utcoffset(now) if False else now)  # placeholder
    # actually next_run = now + period_days
    from datetime import timedelta
    next_run = (now + timedelta(days=int(period_days))).isoformat()
    last_run = now.isoformat()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO recurring_templates (user_id, client_id, period_days, custom_fields_json, last_run, next_run, active, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (user_id, client_id, int(period_days), custom_fields_json, last_run, next_run, 1, now.isoformat()),
    )
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    print(f"[RECURRING] template {rid} client={client_id} next={next_run}")
    return rid

def list_recurring(user_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM recurring_templates WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()
    conn.close()
    return rows

def get_due_recurring():
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    rows = conn.execute("SELECT * FROM recurring_templates WHERE active=1 AND next_run <= ?", (now,)).fetchall()
    conn.close()
    return rows

def update_recurring_next_run(rid, next_run_iso):
    conn = get_conn()
    conn.execute("UPDATE recurring_templates SET last_run=?, next_run=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), next_run_iso, rid))
    conn.commit()
    conn.close()

# ---------- chase (overdue reminders) ----------
def set_invoice_due(iid, due_iso):
    conn = get_conn()
    conn.execute("UPDATE invoices SET due_date=? WHERE id=?", (due_iso, iid))
    conn.commit()
    conn.close()

def mark_invoice_paid(iid, user_id=None):
    conn = get_conn()
    if user_id:
        conn.execute("UPDATE invoices SET paid=1, status='paid' WHERE id=? AND user_id=?", (iid, user_id))
    else:
        conn.execute("UPDATE invoices SET paid=1, status='paid' WHERE id=?", (iid,))
    conn.commit()
    conn.close()

def toggle_chase_pause(iid, user_id=None):
    conn = get_conn()
    q = "UPDATE invoices SET chase_paused=1-COALESCE(chase_paused,0) WHERE id=?"
    params = [iid]
    if user_id:
        q += " AND user_id=?"
        params.append(user_id)
    conn.execute(q, params)
    conn.commit()
    conn.close()

def get_overdue(user_id=None):
    conn = get_conn()
    q = ("SELECT i.*, c.name client_name, c.currency client_currency, c.email client_email "
         "FROM invoices i LEFT JOIN clients c ON c.id=i.client_id "
         "WHERE i.status='sent' AND COALESCE(i.paid,0)=0 AND COALESCE(i.chase_paused,0)=0 "
         "AND i.due_date IS NOT NULL")
    params = []
    if user_id:
        q += " AND i.user_id=?"
        params.append(user_id)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return rows

def reminder_done(invoice_id, day):
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM reminders WHERE invoice_id=? AND day=?", (invoice_id, day)).fetchone()
    conn.close()
    return bool(row)

def log_reminder(user_id, invoice_id, day):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO reminders(user_id,invoice_id,day,sent_at) VALUES(?,?,?,?)",
            (user_id, invoice_id, day, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    except Exception:
        pass
    conn.close()
