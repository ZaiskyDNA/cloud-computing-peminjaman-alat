#!/usr/bin/env bash
# Membuat (atau memperbarui) seluruh resource: DynamoDB, Lambda, API Gateway.
# Jalankan dari root repo, di AWS CloudShell atau terminal yang sudah diisi
# kredensial dari menu "AWS Details" Learner Lab.
#
#   bash scripts/deploy.sh
#
# Skrip ini aman dijalankan berulang: resource yang sudah ada tidak dibuat ulang.

set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
TABLE="Loans"
FUNC="loans-handler"
API_NAME="loans-api"
ROUTES=("POST /loans" "GET /loans" "GET /loans/{loanId}" "PUT /loans/{loanId}" "DELETE /loans/{loanId}")

export AWS_DEFAULT_REGION="$REGION"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
# Learner Lab tidak mengizinkan pembuatan IAM role baru, jadi dipakai LabRole.
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/LabRole"
echo "Akun: $ACCOUNT_ID | Region: $REGION | Role: $ROLE_ARN"

# ------------------------------------------------------------------ DynamoDB
if aws dynamodb describe-table --table-name "$TABLE" >/dev/null 2>&1; then
  echo "[dynamodb] Tabel $TABLE sudah ada"
else
  echo "[dynamodb] Membuat tabel $TABLE (on-demand)"
  aws dynamodb create-table \
    --table-name "$TABLE" \
    --attribute-definitions AttributeName=loanId,AttributeType=S \
    --key-schema AttributeName=loanId,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST >/dev/null
  aws dynamodb wait table-exists --table-name "$TABLE"
fi

# -------------------------------------------------------------------- Lambda
mkdir -p build
rm -f build/function.zip
(cd src && zip -q ../build/function.zip handler.py)

if aws lambda get-function --function-name "$FUNC" >/dev/null 2>&1; then
  echo "[lambda] Memperbarui kode $FUNC"
  aws lambda update-function-code --function-name "$FUNC" \
    --zip-file fileb://build/function.zip >/dev/null
else
  echo "[lambda] Membuat fungsi $FUNC"
  aws lambda create-function \
    --function-name "$FUNC" \
    --runtime python3.12 \
    --handler handler.lambda_handler \
    --role "$ROLE_ARN" \
    --zip-file fileb://build/function.zip \
    --memory-size 128 \
    --timeout 10 \
    --environment "Variables={TABLE_NAME=$TABLE}" >/dev/null
fi
aws lambda wait function-active-v2 --function-name "$FUNC"
FUNC_ARN=$(aws lambda get-function --function-name "$FUNC" --query Configuration.FunctionArn --output text)

# --------------------------------------------------------------- API Gateway
API_ID=$(aws apigatewayv2 get-apis --query "Items[?Name=='$API_NAME'].ApiId | [0]" --output text)

if [[ "$API_ID" == "None" || -z "$API_ID" ]]; then
  echo "[apigateway] Membuat HTTP API $API_NAME"
  API_ID=$(aws apigatewayv2 create-api --name "$API_NAME" --protocol-type HTTP \
    --query ApiId --output text)

  INTEGRATION_ID=$(aws apigatewayv2 create-integration \
    --api-id "$API_ID" \
    --integration-type AWS_PROXY \
    --integration-uri "$FUNC_ARN" \
    --payload-format-version 2.0 \
    --query IntegrationId --output text)

  for route in "${ROUTES[@]}"; do
    aws apigatewayv2 create-route --api-id "$API_ID" \
      --route-key "$route" --target "integrations/$INTEGRATION_ID" >/dev/null
    echo "[apigateway] Route dibuat: $route"
  done

  aws apigatewayv2 create-stage --api-id "$API_ID" \
    --stage-name '$default' --auto-deploy >/dev/null

  aws lambda add-permission \
    --function-name "$FUNC" \
    --statement-id apigateway-invoke \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:${REGION}:${ACCOUNT_ID}:${API_ID}/*/*" >/dev/null
else
  echo "[apigateway] API $API_NAME sudah ada ($API_ID)"
fi

API_URL="https://${API_ID}.execute-api.${REGION}.amazonaws.com"
echo "$API_URL" > .api_url
echo
echo "Selesai. Endpoint: $API_URL"
echo "Lanjutkan dengan: bash scripts/smoke_test.sh"
