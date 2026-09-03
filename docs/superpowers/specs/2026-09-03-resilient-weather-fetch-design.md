# Resilient Weather Fetch Design

## Problem

The hourly workflow treats every transient upstream failure as a terminal build
failure. Recent failures include Open-Meteo HTTP 500 responses, empty response
bodies, read and TLS handshake timeouts, plus one CMA network-unreachable error.

## Decision

Keep real failures visible, but absorb transient failures inside the standard
library HTTP client:

- Attempt each JSON request up to four times with 20-second timeouts.
- Wait 2, 4, and 8 seconds between attempts.
- Retry timeouts, network/TLS errors, HTTP 429 and 5xx responses, incomplete HTTP
  reads, empty or invalid JSON, and structurally invalid provider payloads.
- Do not retry deterministic HTTP 4xx responses other than 429.
- Log each retry to stderr with provider, attempt number, error, and delay.
- Raise a single provider-specific error after the final attempt.

The workflow will use `--alerts auto` for Shanghai. CMA failures then produce a
warning and a forecast-only calendar instead of failing the deployment. The
forecast remains mandatory: exhausted Open-Meteo retries still fail the job and
generate an actionable notification.

## Scope

- Add a shared JSON request helper in `weather_ics.py` and use it for Open-Meteo
  and CMA.
- Add deterministic unit tests using fake HTTP responses and patched sleep.
- Change the workflow's Shanghai command from `--alerts cma` to `--alerts auto`.
- Update README deployment behavior.
- Add no dependencies and preserve the existing CLI interface.

## Success Criteria

- A retryable failure followed by a valid response succeeds.
- Empty/invalid JSON is retried.
- HTTP 400 fails immediately without sleeping.
- Four retryable failures raise after exactly four attempts.
- Existing ICS generation tests remain green under Python 3.12.
- The workflow uses CMA auto-degradation.
