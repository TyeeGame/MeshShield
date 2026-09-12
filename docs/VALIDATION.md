# Validation record — 2026-09-12

## Executed successfully

- **18 Python unittest cases** with runtime and HTTP test dependencies installed. Includes actual FastAPI lifespan/HTTP requests through TestClient, serialized bridge retries and disconnect/reconnect using an injected transport, simulated flood isolation, rate/quarantine rules, command idempotency, detector training/held-out normal/anomaly cases, partial-window rejection, node/gateway freshness, and pending/acknowledged UI state.
- Portable C++ protocol/policy/command parser compiled with host Clang using C++11, `-Wall -Wextra -pedantic`; ran successfully. Also passed **UndefinedBehaviorSanitizer**. Verified CRC known-answer packet, wraparound, refill/expiry, rolling violations, and malformed command inputs. This is not a Particle build.
- `node --check dashboard/app.js` passed (syntax check only; Node is not a runtime requirement).
- `python3 -m compileall -q backend simulator scripts tests` passed.
- `scripts/sync_shared.py --check` and `git diff --check` passed.
- Live localhost Uvicorn simulator and browser: both nodes healthy; real-time clean baseline completed; node 2 at 4.00 msg/s exceeded the learned 1.75 msg/s threshold with zero fixed-policy blocks before containment; node 1 stayed healthy. Enabling automatic containment produced acknowledged quarantine on node 2. Manual quarantine and release controls exercised after fixing status refreshes to preserve stable button elements.
- Dashboard visually inspected in a narrow app viewport. Mode badge, node metrics, learned state, traffic graphs, quarantine countdown, and incident/command status rendered correctly. No hardware control was substituted for a physical button.

## Not validated / environment limits

- **No Particle CLI or ARM Device OS toolchain was installed**, so the Argon and Xenon Particle projects have **not been compiled**, linked, or flashed. Compatibility was checked against official Particle docs and v1.5.2 sources; this is not equivalent to compilation.
- **No physical boards/wiring were tested.** I²C callback behavior, bus recovery under electrical faults, USB backpressure on actual boards, RGB, button debounce, and standalone device/system-part provisioning require a bench check.
- PowerShell/Windows driver/COM-port/Workbench setup was documented but not executed. Software tests ran on macOS with Python 3.9; the README recommends Python 3.11/3.12 for installation.
- AddressSanitizer could not initialize in this macOS environment (`sanitizer_malloc_mac.inc:189` assertion), including outside the sandbox. No AddressSanitizer pass is claimed; ordinary native and UndefinedBehaviorSanitizer runs passed.

Simulation, HTTP tests, and host C++ tests must not be reported as hardware tests. The concrete next hardware gates are the two pinned Particle builds (Xenon compiled for each node setting), DFU/system-part installation, healthy two-node polling, and unplug/stuck-bus/USB-backpressure bench tests.
