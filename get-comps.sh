#!/bin/bash
# Kiavi ARV + comp puller
# Usage: bash get-comps.sh "123 Main St, Miami, FL 33101" [purchasePrice] [rehabBudget]

ADDRESS="$1"
PURCHASE="${2:-0}"
REHAB="${3:-0}"

if [ -z "$ADDRESS" ]; then
  echo "ERROR: No address provided"
  exit 1
fi

cd /root/buying-hero-bot && node kiavi-arv.js "$ADDRESS" "$PURCHASE" "$REHAB"
