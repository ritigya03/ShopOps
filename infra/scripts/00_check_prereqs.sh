#!/usr/bin/env bash
set -euo pipefail

command -v aws >/dev/null 2>&1 || {
  echo "aws CLI not found. Install it: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
  exit 1
}

aws sts get-caller-identity --output table
echo "AWS CLI is configured. Region: $(aws configure get region)"
