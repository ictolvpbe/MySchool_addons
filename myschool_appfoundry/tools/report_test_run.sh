#!/usr/bin/env bash
#
# report_test_run.sh — draai de Odoo-tests van een module tegen een
# wegwerp-DB, parse het resultaat en push het naar de AppFoundry-app via
# de MCP-tool appfoundry_report_test_run.
#
# Gebruik:
#   MCP_KEY=<claude-mcp api-key> \
#   ./report_test_run.sh <module> <test_tag> <appfoundry_project_code>
#
# Voorbeeld:
#   MCP_KEY=xxx ./report_test_run.sh myschool_core myschool_account SRVMGR
#
# Vereist: een geldige claude-mcp X-API-Key (MCP_KEY), python-venv,
# en netwerk naar de MCP-endpoint. De DB is een wegwerp-DB (test_<module>).
set -euo pipefail

MODULE="${1:?module vereist}"
TEST_TAG="${2:?test_tag vereist}"
PROJECT="${3:?appfoundry project code vereist}"

: "${MCP_KEY:?zet MCP_KEY=<claude-mcp api-key>}"
MCP_URL="${MCP_URL:-https://myschool-ict.olvp.be/mcp}"
ODOO_BIN="${ODOO_BIN:-/home/demm/PyCharm/odoo-myschool/odoo/odoo-bin}"
PYTHON="${PYTHON:-/home/demm/PyCharm/.venv/bin/python}"
CONF="${CONF:-/home/demm/PyCharm/odoo-myschool/config/odoo.conf}"
DB="test_${MODULE}_report"
LOG="$(mktemp)"

BRANCH="$(git -C "$(dirname "$0")" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"
COMMIT="$(git -C "$(dirname "$0")" rev-parse --short HEAD 2>/dev/null || echo '')"

echo ">> Verse install + tests van $MODULE (tag: $TEST_TAG) op DB $DB ..."
PGPASSWORD="${PGPASSWORD:-}" dropdb --if-exists -h localhost -U myschool "$DB" 2>/dev/null || true
START=$(date +%s)
"$PYTHON" "$ODOO_BIN" -c "$CONF" -d "$DB" \
    --http-port=8978 --gevent-port=8979 --no-http --stop-after-init \
    --max-cron-threads=0 -i "$MODULE" --test-enable --test-tags "$TEST_TAG" \
    --log-level=test > "$LOG" 2>&1 || true
DURATION=$(( $(date +%s) - START ))

# Odoo logt: "N failed, M error(s) of T tests when loading database '...'"
LINE="$(grep -oE '[0-9]+ failed, [0-9]+ error\(s\) of [0-9]+ tests' "$LOG" | tail -1 || true)"
if [[ -z "$LINE" ]]; then
    echo "!! Geen testresultaat-regel gevonden in $LOG" >&2
    tail -20 "$LOG" >&2
    exit 1
fi
FAILED=$(echo "$LINE" | grep -oE '^[0-9]+')
ERRORS=$(echo "$LINE" | grep -oE '[0-9]+ error' | grep -oE '^[0-9]+')
TOTAL=$(echo "$LINE"  | grep -oE 'of [0-9]+ tests' | grep -oE '[0-9]+')
echo ">> $LINE  (duur ${DURATION}s)"

# Bouw de JSON-payload veilig met python (geen wrap/escape-problemen).
PAYLOAD=$("$PYTHON" - "$PROJECT" "$TOTAL" "$FAILED" "$ERRORS" "$TEST_TAG" "$DURATION" "$BRANCH" "$COMMIT" <<'PY'
import json, sys
project, total, failed, errors, tag, dur, branch, commit = sys.argv[1:9]
print(json.dumps({
    "jsonrpc": "2.0", "id": 1, "method": "tools/call",
    "params": {"name": "appfoundry_report_test_run", "arguments": {
        "project": project, "total": int(total), "failed": int(failed),
        "errors": int(errors), "test_tag": tag, "duration": float(dur),
        "branch": branch or None, "commit": commit or None,
    }},
}))
PY
)

echo ">> Push naar AppFoundry ($PROJECT) ..."
curl -s -X POST "$MCP_URL" \
    -H "X-API-Key: $MCP_KEY" -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d "$PAYLOAD"
echo
