"""
Lambda handler untuk API Peminjaman Alat Laboratorium.

Satu fungsi menangani seluruh route CRUD. Routing dilakukan berdasarkan
`routeKey` dari API Gateway HTTP API (payload format 2.0), misalnya
"POST /loans" atau "GET /loans/{loanId}".
"""

import base64
import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

TABLE_NAME = os.environ.get("TABLE_NAME", "Loans")

REQUIRED_FIELDS = ("equipmentName", "borrowerName", "borrowerId", "loanDate", "dueDate")
UPDATABLE_FIELDS = ("equipmentName", "borrowerName", "borrowerId", "loanDate", "dueDate", "status")
VALID_STATUS = ("DIPINJAM", "DIKEMBALIKAN", "TERLAMBAT")

_table = None


def get_table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(TABLE_NAME)
    return _table


def _json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"Tipe tidak dapat diserialisasi: {type(value)}")


def response(status_code, body=None):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=_json_default) if body is not None else "",
    }


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_body(event):
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None, "Body bukan JSON yang valid"
    if not isinstance(data, dict):
        return None, "Body harus berupa objek JSON"
    return data, None


def _valid_date(value):
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


def _validate(data, partial=False):
    if not partial:
        missing = [f for f in REQUIRED_FIELDS if not data.get(f)]
        if missing:
            return "Field wajib belum diisi: " + ", ".join(missing)
    for field in ("loanDate", "dueDate"):
        if field in data and not _valid_date(data[field]):
            return f"{field} harus berformat YYYY-MM-DD"
    if "loanDate" in data and "dueDate" in data and data["dueDate"] < data["loanDate"]:
        return "dueDate tidak boleh lebih awal dari loanDate"
    if "status" in data and data["status"] not in VALID_STATUS:
        return "status harus salah satu dari: " + ", ".join(VALID_STATUS)
    return None


# --------------------------------------------------------------- operasi CRUD

def create_loan(event):
    data, err = _parse_body(event)
    if err:
        return response(400, {"message": err})
    err = _validate(data)
    if err:
        return response(400, {"message": err})

    timestamp = _now()
    item = {f: data[f] for f in REQUIRED_FIELDS}
    item.update({
        "loanId": str(uuid.uuid4()),
        "status": data.get("status", "DIPINJAM"),
        "createdAt": timestamp,
        "updatedAt": timestamp,
    })

    get_table().put_item(Item=item, ConditionExpression="attribute_not_exists(loanId)")
    return response(201, item)


def list_loans(event):
    result = get_table().scan(Limit=100)
    items = result.get("Items", [])
    return response(200, {"count": len(items), "items": items})


def get_loan(event, loan_id):
    item = get_table().get_item(Key={"loanId": loan_id}).get("Item")
    if not item:
        return response(404, {"message": f"Peminjaman {loan_id} tidak ditemukan"})
    return response(200, item)


def update_loan(event, loan_id):
    data, err = _parse_body(event)
    if err:
        return response(400, {"message": err})
    changes = {k: v for k, v in data.items() if k in UPDATABLE_FIELDS}
    if not changes:
        return response(400, {"message": "Tidak ada field yang dapat diperbarui"})
    err = _validate(changes, partial=True)
    if err:
        return response(400, {"message": err})

    changes["updatedAt"] = _now()
    names = {f"#{k}": k for k in changes}
    values = {f":{k}": v for k, v in changes.items()}
    expression = "SET " + ", ".join(f"#{k} = :{k}" for k in changes)

    try:
        result = get_table().update_item(
            Key={"loanId": loan_id},
            UpdateExpression=expression,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression="attribute_exists(loanId)",
            ReturnValues="ALL_NEW",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return response(404, {"message": f"Peminjaman {loan_id} tidak ditemukan"})
        raise
    return response(200, result["Attributes"])


def delete_loan(event, loan_id):
    try:
        get_table().delete_item(
            Key={"loanId": loan_id},
            ConditionExpression="attribute_exists(loanId)",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return response(404, {"message": f"Peminjaman {loan_id} tidak ditemukan"})
        raise
    return response(204)


# ---------------------------------------------------------------- entry point

def lambda_handler(event, context):
    route = event.get("routeKey", "")
    loan_id = (event.get("pathParameters") or {}).get("loanId")

    try:
        if route == "POST /loans":
            return create_loan(event)
        if route == "GET /loans":
            return list_loans(event)
        if route == "GET /loans/{loanId}":
            return get_loan(event, loan_id)
        if route == "PUT /loans/{loanId}":
            return update_loan(event, loan_id)
        if route == "DELETE /loans/{loanId}":
            return delete_loan(event, loan_id)
        return response(404, {"message": f"Route tidak dikenal: {route}"})
    except ClientError as exc:
        print(f"DynamoDB error: {exc}")
        return response(500, {"message": "Gagal mengakses database"})
