#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_SCRIPT="${SCRIPT_DIR}/verify_deployment_health.sh"

pass_count=0
fail_count=0

assert_contains() {
  local haystack="$1"
  local needle="$2"
  local message="$3"
  if [[ "${haystack}" == *"${needle}"* ]]; then
    pass_count=$((pass_count + 1))
  else
    fail_count=$((fail_count + 1))
    echo "FAIL: ${message}"
    echo "  expected to find: ${needle}"
    echo "  in output: ${haystack}"
  fi
}

assert_eq() {
  local actual="$1"
  local expected="$2"
  local message="$3"
  if [[ "${actual}" == "${expected}" ]]; then
    pass_count=$((pass_count + 1))
  else
    fail_count=$((fail_count + 1))
    echo "FAIL: ${message}"
    echo "  expected: ${expected}"
    echo "  actual:   ${actual}"
  fi
}

run_case() {
  local case_name="$1"
  local sequence="$2"
  local include_heroku="$3"

  local tempdir
  tempdir="$(mktemp -d)"
  local mockbin="${tempdir}/bin"
  mkdir -p "${mockbin}"

  cat >"${mockbin}/curl" <<'MOCKCURL'
#!/usr/bin/env bash
set -euo pipefail

output_file=""
write_format=""
url=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -o)
      output_file="$2"
      shift 2
      ;;
    -w)
      write_format="$2"
      shift 2
      ;;
    --max-time)
      shift 2
      ;;
    -s|-S|-L)
      shift
      ;;
    *)
      url="$1"
      shift
      ;;
  esac
done

counter_file="${MOCK_COUNTER_FILE}"
state_file="${MOCK_SEQUENCE_FILE}"
count=0
if [[ -f "${counter_file}" ]]; then
  count="$(cat "${counter_file}")"
fi
count=$((count + 1))
echo "${count}" >"${counter_file}"

IFS=',' read -ra statuses <<<"${MOCK_STATUS_SEQUENCE}"
idx=$((count - 1))
status="${statuses[$idx]:-${statuses[-1]}}"

echo "${url} attempt ${count}" >"${output_file}"
printf "%s" "${status}"

if [[ "${status}" == "000" ]]; then
  echo "simulated connection failure" >&2
  exit 1
fi
MOCKCURL

  chmod +x "${mockbin}/curl"

  if [[ "${include_heroku}" == "yes" ]]; then
    cat >"${mockbin}/heroku" <<'MOCKHEROKU'
#!/usr/bin/env bash
set -euo pipefail

echo "$*" >>"${MOCK_HEROKU_LOG}"
exit 0
MOCKHEROKU
    chmod +x "${mockbin}/heroku"
  fi

  local output
  local exit_code=0
  set +e
  output="$(
    PATH="${mockbin}:${PATH}" \
    MOCK_COUNTER_FILE="${tempdir}/counter" \
    MOCK_SEQUENCE_FILE="${tempdir}/sequence" \
    MOCK_STATUS_SEQUENCE="${sequence}" \
    MOCK_HEROKU_LOG="${tempdir}/heroku.log" \
    HEALTH_URL="https://example.com/api/v1/health" \
    HEROKU_APP_NAME="test-app" \
    HEALTH_INITIAL_DELAY_SECONDS=0 \
    HEALTH_RETRY_DELAY_SECONDS=0 \
    HEALTH_MAX_ATTEMPTS=5 \
    "${TARGET_SCRIPT}" 2>&1
  )"
  exit_code=$?
  set -e

  echo "${output}" >"${tempdir}/output.log"
  echo "${exit_code}" >"${tempdir}/exit_code"
  echo "${tempdir}"
}

# Case 1: retries and succeeds
tmp1="$(run_case success_after_retries "503,503,200" yes)"
out1="$(cat "${tmp1}/output.log")"
code1="$(cat "${tmp1}/exit_code")"
assert_eq "${code1}" "0" "script exits 0 when health eventually succeeds"
assert_contains "${out1}" "Attempt 1/5 failed" "logs first failed attempt"
assert_contains "${out1}" "Health check passed on attempt 3/5" "logs successful attempt number"
heroku_calls1="$(cat "${tmp1}/heroku.log")"
assert_contains "${heroku_calls1}" "ps --app test-app" "calls heroku ps"
assert_contains "${heroku_calls1}" "ps:wait --app test-app" "calls heroku ps:wait"

# Case 2: exhaust attempts and fail
tmp2="$(run_case fail_after_retries "503,503,503,503,503" no)"
out2="$(cat "${tmp2}/output.log")"
code2="$(cat "${tmp2}/exit_code")"
assert_eq "${code2}" "1" "script exits non-zero when health never succeeds"
assert_contains "${out2}" "Health check failed after 5 attempts" "logs final failure summary"
assert_contains "${out2}" "Response body (first 500 chars):" "logs response body details on failure"

if (( fail_count > 0 )); then
  echo "${pass_count} assertions passed, ${fail_count} assertions failed"
  exit 1
fi

echo "All ${pass_count} assertions passed"
