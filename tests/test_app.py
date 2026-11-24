"""Uji lokal aplikasi Flask tanpa AWS dan tanpa MySQL.

Koneksi database diganti dengan tiruan sederhana sehingga uji ini bisa
dijalankan di laptop tanpa memakai kredit AWS. Uji end-to-end terhadap RDS
dilakukan oleh scripts/smoke_test.sh setelah deploy.
"""

import os
import sys
from datetime import date, datetime

import pytest

for key, value in {"DB_HOST": "localhost", "DB_USER": "test",
                   "DB_PASSWORD": "test", "DB_NAME": "loansdb"}.items():
    os.environ.setdefault(key, value)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import app as api  # noqa: E402

SAMPLE = {
    "equipmentName": "Osiloskop Rigol DS1054Z",
    "borrowerName": "Budi Santoso",
    "borrowerId": "512345",
    "loanDate": "2026-11-24",
    "dueDate": "2026-11-27",
}


class FakeDB:
    """Tiruan minimal tabel loans untuk perintah SQL yang dipakai app.py."""

    def __init__(self):
        self.rows = {}
        self.rowcount = 0
        self._result = []

    # context manager untuk koneksi dan cursor
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return self

    def execute(self, sql, params=()):
        sql = " ".join(sql.split())
        if sql.startswith("INSERT"):
            cols = sql[sql.index("(") + 1:sql.index(")")].split(", ")
            row = dict(zip(cols, params))
            for key in ("loan_date", "due_date"):
                row[key] = date.fromisoformat(row[key])
            self.rows[row["loan_id"]] = row
        elif sql.startswith("SELECT * FROM loans WHERE"):
            row = self.rows.get(params[0])
            self._result = [dict(row)] if row else []
        elif sql.startswith("SELECT * FROM loans"):
            self._result = [dict(r) for r in self.rows.values()]
        elif sql.startswith("UPDATE"):
            sets = sql[len("UPDATE loans SET "):sql.index(" WHERE")].split(", ")
            row = self.rows[params[-1]]
            for assignment, value in zip(sets, params[:-1]):
                row[assignment.split(" = ")[0]] = value
        elif sql.startswith("DELETE"):
            self.rowcount = 1 if self.rows.pop(params[0], None) else 0

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return self._result


@pytest.fixture
def client(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(api, "connect", lambda: db)
    return api.app.test_client()


def test_crud_lengkap(client):
    res = client.post("/loans", json=SAMPLE)
    assert res.status_code == 201
    loan = res.get_json()
    assert loan["status"] == "DIPINJAM"
    loan_id = loan["loanId"]

    res = client.get(f"/loans/{loan_id}")
    assert res.status_code == 200 and res.get_json()["borrowerName"] == "Budi Santoso"

    res = client.put(f"/loans/{loan_id}", json={"status": "DIKEMBALIKAN"})
    assert res.status_code == 200 and res.get_json()["status"] == "DIKEMBALIKAN"

    res = client.get("/loans")
    assert res.status_code == 200 and res.get_json()["count"] == 1

    assert client.delete(f"/loans/{loan_id}").status_code == 204
    assert client.get(f"/loans/{loan_id}").status_code == 404


def test_field_wajib_kosong(client):
    res = client.post("/loans", json={"equipmentName": "Multimeter"})
    assert res.status_code == 400
    assert "borrowerName" in res.get_json()["message"]


def test_tanggal_kembali_sebelum_tanggal_pinjam(client):
    res = client.post("/loans", json=dict(SAMPLE, dueDate="2026-11-20"))
    assert res.status_code == 400


def test_id_tidak_ada(client):
    assert client.put("/loans/tidak-ada", json={"status": "DIKEMBALIKAN"}).status_code == 404
    assert client.delete("/loans/tidak-ada").status_code == 404


def test_status_tidak_valid(client):
    res = client.post("/loans", json=dict(SAMPLE, status="HILANG"))
    assert res.status_code == 400


def test_format_tanggal_ke_json():
    row = {col: None for col in api.COLUMNS.values()}
    row.update(loan_date=date(2026, 11, 24), due_date=date(2026, 11, 27),
               created_at=datetime(2026, 11, 24, 13, 0, 0),
               updated_at=datetime(2026, 11, 24, 13, 0, 0))
    out = api.to_api(row)
    assert out["loanDate"] == "2026-11-24"
    assert out["createdAt"] == "2026-11-24T13:00:00+00:00"
