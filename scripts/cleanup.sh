#!/usr/bin/env bash
# Menghapus seluruh resource proyek. Jalankan hanya setelah semua bukti
# (screenshot dan output tes) sudah tersimpan.
#
#   bash scripts/cleanup.sh

set -uo pipefail

export AWS_DEFAULT_REGION="${AWS_REGION:-us-east-1}"

API_ID=$(aws apigatewayv2 get-apis --query "Items[?Name=='loans-api'].ApiId | [0]" --output text)
if [[ "$API_ID" != "None" && -n "$API_ID" ]]; then
  aws apigatewayv2 delete-api --api-id "$API_ID" && echo "API $API_ID dihapus"
fi

aws lambda delete-function --function-name loans-handler 2>/dev/null && echo "Lambda dihapus"
aws logs delete-log-group --log-group-name /aws/lambda/loans-handler 2>/dev/null && echo "Log group dihapus"
aws dynamodb delete-table --table-name Loans >/dev/null 2>&1 && echo "Tabel Loans dihapus"

rm -f .api_url
echo "Pembersihan selesai."
