"""Uji lokal handler dengan DynamoDB tiruan (moto). Tidak memakai kredit AWS."""

import json
import os
import sys

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ["TABLE_NAME"] = "Loans"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import handler  # noqa: E402

SAMPLE = {
    "equipmentName": "Osiloskop Rigol DS1054Z",
    "borrowerName": "Budi Santoso",
    "borrowerId": "512345",
    "loanDate": "2026-11-24",
    "dueDate": "2026-11-27",
}


@pytest.fixture(autouse=True)
def table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="Loans",
            KeySchema=[{"AttributeName": "loanId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "loanId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        handler._table = None
        yield
        handler._table = None


def call(route, body=None, loan_id=None):
    event = {"routeKey": route}
    if body is not None:
        event["body"] = json.dumps(body)
    if loan_id:
        event["pathParameters"] = {"loanId": loan_id}
    res = handler.lambda_handler(event, None)
    return res["statusCode"], (json.loads(res["body"]) if res["body"] else None)


def test_crud_lengkap():
    status, created = call("POST /loans", SAMPLE)
    assert status == 201
    assert created["status"] == "DIPINJAM"
    loan_id = created["loanId"]

    status, item = call("GET /loans/{loanId}", loan_id=loan_id)
    assert status == 200 and item["borrowerName"] == "Budi Santoso"

    status, item = call("PUT /loans/{loanId}", {"status": "DIKEMBALIKAN"}, loan_id)
    assert status == 200 and item["status"] == "DIKEMBALIKAN"

    status, listing = call("GET /loans")
    assert status == 200 and listing["count"] == 1

    status, _ = call("DELETE /loans/{loanId}", loan_id=loan_id)
    assert status == 204

    status, _ = call("GET /loans/{loanId}", loan_id=loan_id)
    assert status == 404


def test_field_wajib_kosong():
    status, body = call("POST /loans", {"equipmentName": "Multimeter"})
    assert status == 400
    assert "borrowerName" in body["message"]


def test_tanggal_kembali_sebelum_tanggal_pinjam():
    status, _ = call("POST /loans", dict(SAMPLE, dueDate="2026-11-20"))
    assert status == 400


def test_id_tidak_ada():
    assert call("PUT /loans/{loanId}", {"status": "DIKEMBALIKAN"}, "tidak-ada")[0] == 404
    assert call("DELETE /loans/{loanId}", loan_id="tidak-ada")[0] == 404


def test_status_tidak_valid():
    status, _ = call("POST /loans", dict(SAMPLE, status="HILANG"))
    assert status == 400
