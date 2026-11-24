#!/usr/bin/env bash
# Menguji endpoint API di EC2 (yang terhubung ke RDS) dan menyimpan hasilnya ke
# evidence/smoke-test-output.txt sebagai bukti konektivitas.
#
#   bash scripts/smoke_test.sh [URL_API]

set -euo pipefail

API_URL="${1:-$(cat .api_url 2>/dev/null || true)}"
if [[ -z "$API_URL" ]]; then
  echo "URL API belum diketahui. Jalankan deploy.sh atau berikan URL sebagai argumen."
  exit 1
fi

mkdir -p evidence
OUT="evidence/smoke-test-output.txt"
: > "$OUT"

log() { echo "$@" | tee -a "$OUT"; }

request() {
  local method="$1" path="$2" body="${3:-}"
  log ""
  log "\$ curl -X $method $API_URL$path"
  if [[ -n "$body" ]]; then log "  body: $body"; fi
  if [[ -n "$body" ]]; then
    RESP=$(curl -s -w '\n%{http_code}' -X "$method" "$API_URL$path" \
      -H 'Content-Type: application/json' -d "$body")
  else
    RESP=$(curl -s -w '\n%{http_code}' -X "$method" "$API_URL$path")
  fi
  STATUS=$(tail -n1 <<< "$RESP")
  BODY=$(sed '$d' <<< "$RESP")
  log "  HTTP $STATUS"
  if [[ -n "$BODY" ]]; then log "  $BODY"; fi
}

log "Smoke test API Peminjaman Alat"
log "Endpoint : $API_URL"
log "Waktu    : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"

request GET /health
request POST /loans '{"equipmentName":"Osiloskop Rigol DS1054Z","borrowerName":"Budi Santoso","borrowerId":"512345","loanDate":"2026-11-24","dueDate":"2026-11-27"}'
LOAN_ID=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["loanId"])' "$BODY")

request GET "/loans/$LOAN_ID"
request PUT "/loans/$LOAN_ID" '{"status":"DIKEMBALIKAN"}'
request GET /loans
request DELETE "/loans/$LOAN_ID"
request GET "/loans/$LOAN_ID"

log ""
log "Selesai. Hasil tersimpan di $OUT"
