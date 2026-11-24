#!/usr/bin/env bash
# Track A (Cloud VM): membuat VPC, security group, RDS MySQL, dan EC2 yang
# menjalankan API Flask. Jalankan dari root repo di terminal Learner Lab /
# Sandbox / CloudShell (region us-east-1).
#
#   bash scripts/deploy.sh
#
# Nilai yang dibuat disimpan di .state agar skrip aman dijalankan ulang.

set -euo pipefail
export AWS_DEFAULT_REGION="${AWS_REGION:-us-east-1}"
export AWS_PAGER=""

P=loans
STATE=.state
touch "$STATE"; chmod 600 "$STATE"
# shellcheck disable=SC1090
source "$STATE"
save() { echo "$1=$2" >> "$STATE"; eval "$1=$2"; }
tag() { echo "ResourceType=$1,Tags=[{Key=Name,Value=$2},{Key=Project,Value=$P}]"; }

AZ1="${AWS_DEFAULT_REGION}a"; AZ2="${AWS_DEFAULT_REGION}b"

# ------------------------------------------------------------------ jaringan
if [[ -z "${VPC_ID:-}" ]]; then
  echo "[vpc] Membuat VPC 10.0.0.0/16"
  save VPC_ID "$(aws ec2 create-vpc --cidr-block 10.0.0.0/16 \
    --tag-specifications "$(tag vpc $P-vpc)" --query Vpc.VpcId --output text)"
  aws ec2 modify-vpc-attribute --vpc-id "$VPC_ID" --enable-dns-hostnames
  aws ec2 wait vpc-available --vpc-ids "$VPC_ID"

  save IGW_ID "$(aws ec2 create-internet-gateway \
    --tag-specifications "$(tag internet-gateway $P-igw)" \
    --query InternetGateway.InternetGatewayId --output text)"
  aws ec2 attach-internet-gateway --vpc-id "$VPC_ID" --internet-gateway-id "$IGW_ID"

  mk_subnet() {  # nama cidr az
    aws ec2 create-subnet --vpc-id "$VPC_ID" --cidr-block "$2" --availability-zone "$3" \
      --tag-specifications "$(tag subnet "$1")" --query Subnet.SubnetId --output text
  }
  save PUB_SUBNET "$(mk_subnet $P-public-a 10.0.1.0/24 "$AZ1")"
  save PRIV_SUBNET_A "$(mk_subnet $P-private-a 10.0.11.0/24 "$AZ1")"
  save PRIV_SUBNET_B "$(mk_subnet $P-private-b 10.0.12.0/24 "$AZ2")"
  aws ec2 modify-subnet-attribute --subnet-id "$PUB_SUBNET" --map-public-ip-on-launch

  save RT_ID "$(aws ec2 create-route-table --vpc-id "$VPC_ID" \
    --tag-specifications "$(tag route-table $P-public-rt)" \
    --query RouteTable.RouteTableId --output text)"
  aws ec2 create-route --route-table-id "$RT_ID" --destination-cidr-block 0.0.0.0/0 \
    --gateway-id "$IGW_ID" >/dev/null
  aws ec2 associate-route-table --route-table-id "$RT_ID" --subnet-id "$PUB_SUBNET" >/dev/null
  echo "[vpc] $VPC_ID: 1 subnet publik, 2 subnet privat"
fi

if [[ -z "${WEB_SG:-}" ]]; then
  save WEB_SG "$(aws ec2 create-security-group --vpc-id "$VPC_ID" --group-name $P-web-sg \
    --description "HTTP publik ke API" --query GroupId --output text)"
  aws ec2 authorize-security-group-ingress --group-id "$WEB_SG" \
    --protocol tcp --port 80 --cidr 0.0.0.0/0 >/dev/null

  save DB_SG "$(aws ec2 create-security-group --vpc-id "$VPC_ID" --group-name $P-db-sg \
    --description "MySQL hanya dari web-sg" --query GroupId --output text)"
  aws ec2 authorize-security-group-ingress --group-id "$DB_SG" \
    --protocol tcp --port 3306 --source-group "$WEB_SG" >/dev/null
  echo "[sg] web-sg $WEB_SG (80 dari internet), db-sg $DB_SG (3306 dari web-sg)"
fi

# ----------------------------------------------------------------------- RDS
if [[ -z "${DB_PASSWORD:-}" ]]; then
  save DB_PASSWORD "$(openssl rand -hex 16)"
fi

if ! aws rds describe-db-instances --db-instance-identifier $P-db >/dev/null 2>&1; then
  aws rds create-db-subnet-group --db-subnet-group-name $P-db-subnets \
    --db-subnet-group-description "Subnet privat RDS" \
    --subnet-ids "$PRIV_SUBNET_A" "$PRIV_SUBNET_B" >/dev/null 2>&1 || true
  echo "[rds] Membuat MySQL db.t3.micro (5-10 menit)"
  aws rds create-db-instance \
    --db-instance-identifier $P-db \
    --engine mysql \
    --db-instance-class db.t3.micro \
    --allocated-storage 20 --storage-type gp2 \
    --master-username admin --master-user-password "$DB_PASSWORD" \
    --db-name loansdb \
    --db-subnet-group-name $P-db-subnets \
    --vpc-security-group-ids "$DB_SG" \
    --no-publicly-accessible --no-multi-az \
    --backup-retention-period 0 --monitoring-interval 0 \
    --tags Key=Project,Value=$P >/dev/null
fi
aws rds wait db-instance-available --db-instance-identifier $P-db
DB_HOST=$(aws rds describe-db-instances --db-instance-identifier $P-db \
  --query 'DBInstances[0].Endpoint.Address' --output text)
echo "[rds] Endpoint: $DB_HOST"

# ----------------------------------------------------------------------- EC2
if [[ -z "${INSTANCE_ID:-}" ]]; then
  USERDATA=$(mktemp)
  {
    echo '#!/bin/bash'
    echo 'set -eux'
    echo 'dnf install -y python3-pip mariadb105'
    echo 'pip3 install flask pymysql'
    echo 'mkdir -p /opt/loans'
    echo "cat > /etc/loans.env <<'ENV'"
    echo "DB_HOST=$DB_HOST"
    echo "DB_USER=admin"
    echo "DB_PASSWORD=$DB_PASSWORD"
    echo "DB_NAME=loansdb"
    echo 'ENV'
    echo 'chmod 600 /etc/loans.env'
    echo "cat > /opt/loans/app.py <<'PY'"
    cat app/app.py
    echo 'PY'
    cat <<'UNIT'
cat > /etc/systemd/system/loans.service <<'SVC'
[Unit]
Description=API Peminjaman Alat
After=network-online.target

[Service]
EnvironmentFile=/etc/loans.env
WorkingDirectory=/opt/loans
ExecStart=/usr/bin/python3 /opt/loans/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVC
systemctl daemon-reload
systemctl enable --now loans
UNIT
  } > "$USERDATA"

  echo "[ec2] Meluncurkan t3.micro (Amazon Linux 2023, LabInstanceProfile)"
  save INSTANCE_ID "$(aws ec2 run-instances \
    --image-id resolve:ssm:/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
    --instance-type t3.micro \
    --subnet-id "$PUB_SUBNET" \
    --security-group-ids "$WEB_SG" \
    --iam-instance-profile Name=LabInstanceProfile \
    --user-data "file://$USERDATA" \
    --tag-specifications "$(tag instance $P-web)" \
    --query 'Instances[0].InstanceId' --output text)"
  rm -f "$USERDATA"
fi
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"
PUBLIC_IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

API_URL="http://$PUBLIC_IP"
echo "$API_URL" > .api_url
echo "[ec2] Menunggu aplikasi siap di $API_URL ..."
for _ in $(seq 1 60); do
  if curl -sf "$API_URL/health" >/dev/null; then break; fi
  sleep 10
done
curl -s "$API_URL/health"; echo
echo
echo "Selesai. Endpoint: $API_URL"
echo "Lanjutkan dengan: bash scripts/smoke_test.sh"
