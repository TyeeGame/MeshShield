# Validation in this checkout

Executed September 12, 2026 (local time), on branch `argon-only-migration`.

- 26 Python unittest tests passed, with no skips, using the project's Python 3.12 virtual environment. Coverage includes traffic modes, handshake gating, reconnect handshake invalidation, independent devices, quarantine expiry without extension, duplicate commands, learned containment, baseline restart and HTTP behavior.
- Node dashboard stalled-request/offline and retry regression passed.
- Shared-header synchronization check and packaging unittest passed.
- `git diff --check` passed.
- Particle CLI 3.50.1 is installed at `%LOCALAPPDATA%\particle\bin\particle.exe`; Workbench extension 1.16.50 is installed, but no local toolchains directory/compiler was found.
- Initial USB discovery failed because Windows lacked the DFU driver (Code 28). Installing WinUSB for Argon DFU Mode made the board discoverable; normal serial mode appeared as COM4.
- After explicit user authorization, Particle cloud compilation succeeded for Argon Device OS 1.5.2. Output: `build/argon.bin`; reported application usage: 9,752 bytes flash and 11,360 bytes RAM. The binary is ignored by Git.
- Portable native C++ tests were not run: no host C++ compiler was found on PATH. Python policy tests do not replace those tests or a Particle build.

## Physical checks reported by the user

The user performed the following checks on one real USB-connected Argon and reported the outcomes in this task. These are manual hardware observations, separate from the automated simulator/fake-serial checks above; no serial trace or measured timing/rate capture was saved.

| Check | Reported result |
|---|---|
| Startup | Steady teal LED, gateway online, both virtual slots healthy |
| UNKNOWN_TYPE, automatic containment off | Blocked packets and quarantine on slot 2 |
| Quarantine expiry after returning NORMAL | Healthy state and teal LED returned without manual release |
| FLOOD, automatic containment off | Rate-limit blocks, quarantine and red LED; slot 1 continued healthy |
| Clean baseline | Training completed automatically |
| ANOMALY with automatic containment on | Slot 2 quarantined, red LED, slot 1 remained healthy |
| Manual release after returning NORMAL | User reported recovery; acknowledgment details were not separately captured |
| Detection after release | A second ANOMALY run quarantined slot 2 again |
| USB unplug with backend running | Gateway and devices became offline |
| Reconnect to the same USB port | Gateway and both slots recovered automatically |

### Setup fault and resolution

The application flash reported success, but the board stayed blinking blue and the gateway stayed offline. `serial identify` confirmed 1.5.2. `serial inspect` showed system module 1512 with **Dependencies: FAIL**: it required radio stack 202 while the installed radio stack was 169. The user module passed integrity, address, platform and dependency checks. Bootloader 502 also passed.

`usb setup-done`, reset, and `usb stop-listening` did not resolve this mismatch. The user entered DFU mode and ran `particle update --target 1.5.2`; it reported success, the LED became steady teal, and the hardware checks above then succeeded. A post-update module inspection was not captured, so the repair is established by successful application operation rather than a recorded final radio-stack version.

Remaining coverage limits: exact physical rates/timing, malformed CRC/version injection, duplicate-command replay on hardware and prolonged endurance were not measured in this manual session. Their relevant software checks remain distinct from physical validation. Local Workbench compilation and native host C++ tests remain unverified.

Migration used only the compatibility-checked patch, against commit `77aeaf20189d97b7fa2bd0fdc67087d7e636bacb`. The ZIP inventory was inspected but not extracted. Original project and Git history were preserved. Migration commit: `31e45bd`. Patch, ZIP, virtual environment and build output are ignored.
