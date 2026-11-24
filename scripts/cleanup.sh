#!/usr/bin/env bash
# Menghapus seluruh resource Track A (EC2, RDS, security group, VPC).
# Jalankan hanya setelah semua bukti (screenshot dan output tes) tersimpan.
#
#   bash scripts/cleanup.sh

set -uo pipefail
export AWS_DEFAULT_REGION="${AWS_REGION:-us-east-1}"
export AWS_PAGER=""

if [[ ! -f .state ]]; then
  echo "File .state tidak ditemukan. Jalankan dari folder tempat deploy.sh dijalankan."
  exit 1
fi
# shellcheck disable=SC1091
source .state

if [[ -n "${INSTANCE_ID:-}" ]]; then
  aws ec2 terminate-instances --instance-ids "$INSTANCE_ID" >/dev/null && echo "[ec2] Menghentikan $INSTANCE_ID"
fi

if aws rds describe-db-instances --db-instance-identifier loans-db >/dev/null 2>&1; then
  echo "[rds] Menghapus loans-db (beberapa menit)"
  aws rds delete-db-instance --db-instance-identifier loans-db \
    --skip-final-snapshot --delete-automated-backups >/dev/null
  aws rds wait db-instance-deleted --db-instance-identifier loans-db
fi
aws rds delete-db-subnet-group --db-subnet-group-name loans-db-subnets 2>/dev/null \
  && echo "[rds] Subnet group dihapus"

if [[ -n "${INSTANCE_ID:-}" ]]; then
  aws ec2 wait instance-terminated --instance-ids "$INSTANCE_ID"
fi

for sg in "${DB_SG:-}" "${WEB_SG:-}"; do
  [[ -n "$sg" ]] && aws ec2 delete-security-group --group-id "$sg" && echo "[sg] $sg dihapus"
done

for subnet in "${PUB_SUBNET:-}" "${PRIV_SUBNET_A:-}" "${PRIV_SUBNET_B:-}"; do
  [[ -n "$subnet" ]] && aws ec2 delete-subnet --subnet-id "$subnet" && echo "[vpc] Subnet $subnet dihapus"
done

[[ -n "${RT_ID:-}" ]] && aws ec2 delete-route-table --route-table-id "$RT_ID"
if [[ -n "${IGW_ID:-}" ]]; then
  aws ec2 detach-internet-gateway --internet-gateway-id "$IGW_ID" --vpc-id "$VPC_ID"
  aws ec2 delete-internet-gateway --internet-gateway-id "$IGW_ID"
fi
[[ -n "${VPC_ID:-}" ]] && aws ec2 delete-vpc --vpc-id "$VPC_ID" && echo "[vpc] $VPC_ID dihapus"

rm -f .state .api_url
echo "Pembersihan selesai."
