#!/usr/bin/env bash
set -euo pipefail

REGION="ap-south-1"
KEY_NAME="shopops-prod"
INSTANCE_TYPE="t3.micro"
INFRA_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_FILE="$INFRA_DIR/outputs.env"

# shellcheck source=/dev/null
source "$OUT_FILE"

AMI_ID="$(aws ec2 describe-images --region "$REGION" \
  --owners 099720109477 \
  --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" \
            "Name=state,Values=available" \
  --query 'sort_by(Images, &CreationDate)[-1].ImageId' --output text)"

SUBNET_ID="$(aws ec2 describe-subnets --region "$REGION" \
  --filters "Name=vpc-id,Values=$VPC_ID" "Name=default-for-az,Values=true" \
  --query 'Subnets[0].SubnetId' --output text)"

INSTANCE_ID="$(aws ec2 run-instances --region "$REGION" \
  --image-id "$AMI_ID" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --security-group-ids "$EC2_SG_ID" \
  --subnet-id "$SUBNET_ID" \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=20,VolumeType=gp3}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=shopops-prod}]' \
  --query 'Instances[0].InstanceId' --output text)"

echo "Waiting for instance $INSTANCE_ID to enter running state..."
aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"

ALLOC_ID="$(aws ec2 allocate-address --region "$REGION" --domain vpc \
  --query 'AllocationId' --output text)"
aws ec2 associate-address --region "$REGION" \
  --instance-id "$INSTANCE_ID" --allocation-id "$ALLOC_ID" >/dev/null

ELASTIC_IP="$(aws ec2 describe-addresses --region "$REGION" \
  --allocation-ids "$ALLOC_ID" --query 'Addresses[0].PublicIp' --output text)"

{
  echo "EC2_INSTANCE_ID=$INSTANCE_ID"
  echo "EC2_ELASTIC_IP=$ELASTIC_IP"
} >> "$OUT_FILE"

echo "EC2 instance $INSTANCE_ID running at $ELASTIC_IP"
