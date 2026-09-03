# Resilient Weather Fetch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent transient Open-Meteo and CMA failures from producing noisy GitHub Actions failures while retaining alerts for sustained forecast outages.

**Architecture:** Add one standard-library JSON fetch helper that owns retry classification, backoff, response parsing, and payload validation. Both providers use the helper; the workflow selects the existing non-fatal CMA mode.

**Tech Stack:** Python 3.12 standard library, `unittest`, GitHub Actions YAML.

## Global Constraints

- No new dependencies.
- Four total attempts with 20-second per-attempt timeout.
- Backoff delays are exactly 2, 4, and 8 seconds.
- Open-Meteo remains a required dependency after retries are exhausted.
- CMA failure is non-fatal in the deployed workflow through `--alerts auto`.

---

### Task 1: Retry and degradation behavior

**Files:**
- Modify: `test_weather_ics.py`
- Modify: `weather_ics.py`
- Modify: `.github/workflows/main.yml`
- Modify: `README.md`

**Interfaces:**
- Consumes: `urllib.request.urlopen`, provider JSON payloads, existing `fetch_forecast` and `fetch_cma_alerts` callers.
- Produces: `_fetch_json(request, source, validate)` returning a validated JSON object or raising after deterministic retry handling.

- [x] **Step 1: Write failing tests**

  Add tests covering HTTP 500 then success, invalid JSON then success, immediate
  HTTP 400 failure, and exhaustion after four timeout failures. Patch
  `weather_ics.time.sleep` so the tests remain deterministic and fast.

- [x] **Step 2: Verify RED**

  Run `/Users/admin/.local/share/mise/installs/python/3.12.13/bin/python3.12 -m unittest -v`.
  Expected: the new tests fail because retry behavior is absent.

- [x] **Step 3: Implement the minimal retry helper**

  Add request headers, retry classification, payload validation, backoff logging,
  and provider-specific final errors. Route both fetch functions through it.

- [x] **Step 4: Verify GREEN**

  Run `/Users/admin/.local/share/mise/installs/python/3.12.13/bin/python3.12 -m unittest -v`.
  Expected: all old and new tests pass with zero failures.

- [x] **Step 5: Update deployment behavior and documentation**

  Change the Shanghai workflow invocation to `--alerts auto` and document that
  transient CMA failures publish forecast-only output with a warning.

- [x] **Step 6: Verify the complete change**

  Run the full unit suite, compile `weather_ics.py`, generate Shanghai and
  Singapore ICS files against live endpoints, validate both contain
  `BEGIN:VCALENDAR` and `END:VCALENDAR`, and inspect `git diff --check`.
