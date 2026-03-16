#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[health-check] %s\n' "$*"
}

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    log "Required environment variable missing: ${name}"
    exit 1
  fi
}

wait_for_heroku_dyno() {
  local app_name="$1"

  if ! command -v heroku >/dev/null 2>&1; then
    log "Heroku CLI is not installed; skipping dyno wait"
    return
  fi

  log "Checking Heroku dyno status for app '${app_name}'"
  if ! heroku ps --app "${app_name}"; then
    log "Unable to fetch dyno status via 'heroku ps'; continuing to health checks"
    return
  fi

  log "Waiting for Heroku dynos to report up via 'heroku ps:wait'"
  if ! heroku ps:wait --app "${app_name}"; then
    log "Heroku dynos did not stabilize before timeout; continuing to explicit health checks"
  fi
}

run_health_checks() {
  local health_url="$1"
  local max_attempts="$2"
  local retry_delay_seconds="$3"
  local curl_timeout_seconds="$4"

  local response_file
  local curl_error_file
  response_file="$(mktemp)"
  curl_error_file="$(mktemp)"

  for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    : >"${response_file}"
    : >"${curl_error_file}"

    local http_status
    if http_status="$(curl -sS -L --max-time "${curl_timeout_seconds}" -o "${response_file}" -w "%{http_code}" "${health_url}" 2>"${curl_error_file}")"; then
      if [[ "${http_status}" == "200" ]]; then
        log "Health check passed on attempt ${attempt}/${max_attempts} (HTTP ${http_status})"
        rm -f "${response_file}" "${curl_error_file}"
        return 0
      fi
    else
      http_status="000"
    fi

    log "Attempt ${attempt}/${max_attempts} failed"
    log "HTTP status: ${http_status}"

    if [[ -s "${curl_error_file}" ]]; then
      log "curl error:"
      sed 's/^/[health-check]   /' "${curl_error_file}"
    fi

    if [[ -s "${response_file}" ]]; then
      log "Response body (first 500 chars):"
      head -c 500 "${response_file}" | sed 's/^/[health-check]   /'
      printf '\n'
    else
      log "Response body is empty"
    fi

    if (( attempt < max_attempts )); then
      log "Retrying in ${retry_delay_seconds}s..."
      sleep "${retry_delay_seconds}"
    fi
  done

  log "Health check failed after ${max_attempts} attempts"
  rm -f "${response_file}" "${curl_error_file}"
  return 1
}

main() {
  require_env "HEALTH_URL"

  local initial_delay_seconds="${HEALTH_INITIAL_DELAY_SECONDS:-30}"
  local max_attempts="${HEALTH_MAX_ATTEMPTS:-10}"
  local retry_delay_seconds="${HEALTH_RETRY_DELAY_SECONDS:-15}"
  local curl_timeout_seconds="${HEALTH_CURL_TIMEOUT_SECONDS:-10}"

  log "Waiting ${initial_delay_seconds}s before checking health endpoint"
  sleep "${initial_delay_seconds}"

  if [[ -n "${HEROKU_APP_NAME:-}" ]]; then
    wait_for_heroku_dyno "${HEROKU_APP_NAME}"
  else
    log "HEROKU_APP_NAME not set; skipping dyno wait"
  fi

  log "Checking health endpoint: ${HEALTH_URL}"
  run_health_checks "${HEALTH_URL}" "${max_attempts}" "${retry_delay_seconds}" "${curl_timeout_seconds}"
}

main "$@"
