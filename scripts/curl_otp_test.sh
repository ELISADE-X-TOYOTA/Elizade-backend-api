#!/usr/bin/env bash
# Trigger a real OTP email through production (same path as the mobile app).
# Uses Railway's Postmark config — no local POSTMARK_TOKEN needed.
#
# Usage:
#   ./scripts/curl_otp_test.sh alieric28@gmail.com
#   API_BASE=https://your-service.up.railway.app/api/v1 ./scripts/curl_otp_test.sh you@outlook.com login

set -euo pipefail

TO="${1:?recipient email}"
PURPOSE="${2:-register}"
API_BASE="${API_BASE:-https://elizade-backend-api-production.up.railway.app/api/v1}"

if [[ "$PURPOSE" == "register" ]]; then
  BODY=$(printf '{"email":"%s","purpose":"register","firstName":"Eric","lastName":"Test"}' "$TO")
else
  BODY=$(printf '{"email":"%s","purpose":"login"}' "$TO")
fi

echo "POST $API_BASE/auth/otp/request"
echo "  to=$TO purpose=$PURPOSE"
echo "(From address = whatever SMTP_FROM_EMAIL is on Railway right now)"
echo

curl -sS -w "\nHTTP %{http_code}\n" -X POST "$API_BASE/auth/otp/request" \
  -H "Content-Type: application/json" \
  -d "$BODY"

echo
echo "200 + verification message → check inbox/spam for Elizade Connect OTP."
echo "502 → Postmark rejected the current From (not verified or wrong SMTP_FROM_EMAIL)."
echo "404 login → register first, or use: $0 $TO login"
