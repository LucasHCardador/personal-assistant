#!/usr/bin/env bash
set -euo pipefail

SUMMARY_TIME="${MORNING_SUMMARY_TIME:-07:30}"
IFS=':' read -r RAW_HOUR RAW_MINUTE <<< "$SUMMARY_TIME"
CRON_HOUR="$((10#${RAW_HOUR:-7}))"
CRON_MINUTE="$((10#${RAW_MINUTE:-30}))"

# Persist container environment variables so cron jobs can load them.
python3 - <<'PY'
import os
import shlex

skip = {"HOSTNAME", "PWD", "SHLVL", "_", "HOME"}
with open("/etc/environment", "w", encoding="utf-8") as fh:
    for key, value in sorted(os.environ.items()):
        if key in skip or not key.isidentifier():
            continue
        fh.write(f"export {key}={shlex.quote(value)}\n")
PY

CRON_FILE="/etc/cron.d/daily-appointments"
cat > "$CRON_FILE" <<EOF
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin
${CRON_MINUTE} ${CRON_HOUR} * * * root cd /app && . /etc/environment && /usr/local/bin/python -m scripts.daily_appointments_summary >> /proc/1/fd/1 2>> /proc/1/fd/2
EOF
chmod 0644 "$CRON_FILE"

echo "Configured daily appointments cron job: ${CRON_MINUTE} ${CRON_HOUR} * * * (TZ=${TZ:-UTC})"
exec cron -f
