"""
API Peminjaman Alat Laboratorium - Track A (EC2 + RDS MySQL).

Aplikasi Flask berjalan di EC2 dan menyimpan data ke Amazon RDS for MySQL.
Konfigurasi koneksi dibaca dari environment variable (DB_HOST, DB_USER,
DB_PASSWORD, DB_NAME).
"""

import json
import os
import uuid
from datetime import date, datetime, timezone

import pymysql
from flask import Flask, Response, request

app = Flask(__name__)

REQUIRED_FIELDS = ("equipmentName", "borrowerName", "borrowerId", "loanDate", "dueDate")
UPDATABLE_FIELDS = REQUIRED_FIELDS + ("status",)
VALID_STATUS = ("DIPINJAM", "DIKEMBALIKAN", "TERLAMBAT")

COLUMNS = {
    "loanId": "loan_id",
    "equipmentName": "equipment_name",
    "borrowerName": "borrower_name",
    "borrowerId": "borrower_id",
    "loanDate": "loan_date",
    "dueDate": "due_date",
    "status": "status",
    "createdAt": "created_at",
    "updatedAt": "updated_at",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS loans (
    loan_id        CHAR(36)     NOT NULL PRIMARY KEY,
    equipment_name VARCHAR(100) NOT NULL,
    borrower_name  VARCHAR(100) NOT NULL,
    borrower_id    VARCHAR(20)  NOT NULL,
    loan_date      DATE         NOT NULL,
    due_date       DATE         NOT NULL,
    status         ENUM('DIPINJAM','DIKEMBALIKAN','TERLAMBAT') NOT NULL DEFAULT 'DIPINJAM',
    created_at     DATETIME     NOT NULL,
    updated_at     DATETIME     NOT NULL
)
"""


def connect():
    return pymysql.connect(
        host=os.environ["DB_HOST"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ.get("DB_NAME", "loansdb"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        connect_timeout=5,
    )


def init_db():
    with connect() as conn, conn.cursor() as cur:
        cur.execute(SCHEMA)


def reply(status, body=None):
    payload = json.dumps(body, default=str) if body is not None else ""
    return Response(payload, status=status, mimetype="application/json")


def to_api(row):
    out = {api: row[col] for api, col in COLUMNS.items()}
    for key in ("loanDate", "dueDate"):
        if isinstance(out[key], date):
            out[key] = out[key].isoformat()
    for key in ("createdAt", "updatedAt"):
        if isinstance(out[key], datetime):
            out[key] = out[key].replace(tzinfo=timezone.utc).isoformat()
    return out


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def valid_date(value):
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


def validate(data, partial=False):
    if not partial:
        missing = [f for f in REQUIRED_FIELDS if not data.get(f)]
        if missing:
            return "Field wajib belum diisi: " + ", ".join(missing)
    for field in ("loanDate", "dueDate"):
        if field in data and not valid_date(data[field]):
            return f"{field} harus berformat YYYY-MM-DD"
    if "loanDate" in data and "dueDate" in data and data["dueDate"] < data["loanDate"]:
        return "dueDate tidak boleh lebih awal dari loanDate"
    if "status" in data and data["status"] not in VALID_STATUS:
        return "status harus salah satu dari: " + ", ".join(VALID_STATUS)
    return None


def body_json():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def fetch(cur, loan_id):
    cur.execute("SELECT * FROM loans WHERE loan_id = %s", (loan_id,))
    return cur.fetchone()


@app.get("/health")
def health():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT VERSION() AS version, NOW() AS db_time")
        row = cur.fetchone()
    return reply(200, {"status": "ok", "database": "connected", **row})


@app.post("/loans")
def create_loan():
    data = body_json()
    if data is None:
        return reply(400, {"message": "Body harus berupa objek JSON"})
    err = validate(data)
    if err:
        return reply(400, {"message": err})
    ts = now()
    item = {f: data[f] for f in REQUIRED_FIELDS}
    item.update(loanId=str(uuid.uuid4()), status=data.get("status", "DIPINJAM"),
                createdAt=ts, updatedAt=ts)
    cols = ", ".join(COLUMNS[k] for k in item)
    marks = ", ".join(["%s"] * len(item))
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"INSERT INTO loans ({cols}) VALUES ({marks})", tuple(item.values()))
        return reply(201, to_api(fetch(cur, item["loanId"])))


@app.get("/loans")
def list_loans():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM loans ORDER BY created_at DESC LIMIT 100")
        items = [to_api(r) for r in cur.fetchall()]
    return reply(200, {"count": len(items), "items": items})


@app.get("/loans/<loan_id>")
def get_loan(loan_id):
    with connect() as conn, conn.cursor() as cur:
        row = fetch(cur, loan_id)
    if not row:
        return reply(404, {"message": f"Peminjaman {loan_id} tidak ditemukan"})
    return reply(200, to_api(row))


@app.put("/loans/<loan_id>")
def update_loan(loan_id):
    data = body_json()
    if data is None:
        return reply(400, {"message": "Body harus berupa objek JSON"})
    changes = {k: v for k, v in data.items() if k in UPDATABLE_FIELDS}
    if not changes:
        return reply(400, {"message": "Tidak ada field yang dapat diperbarui"})
    err = validate(changes, partial=True)
    if err:
        return reply(400, {"message": err})
    changes["updatedAt"] = now()
    sets = ", ".join(f"{COLUMNS[k]} = %s" for k in changes)
    with connect() as conn, conn.cursor() as cur:
        if not fetch(cur, loan_id):
            return reply(404, {"message": f"Peminjaman {loan_id} tidak ditemukan"})
        cur.execute(f"UPDATE loans SET {sets} WHERE loan_id = %s",
                    (*changes.values(), loan_id))
        return reply(200, to_api(fetch(cur, loan_id)))


@app.delete("/loans/<loan_id>")
def delete_loan(loan_id):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM loans WHERE loan_id = %s", (loan_id,))
        if cur.rowcount == 0:
            return reply(404, {"message": f"Peminjaman {loan_id} tidak ditemukan"})
    return reply(204)


@app.errorhandler(pymysql.MySQLError)
def db_error(exc):
    app.logger.error("MySQL error: %s", exc)
    return reply(500, {"message": "Gagal mengakses database"})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "80")))
