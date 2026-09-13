Once setup, run:
.\.venv\Scripts\python.exe -m backend --port COM4


# MeshShield

A wired IoT application-layer security demo: two Particle Xenons → independent I²C buses → Particle Argon → USB → Python dashboard. Xenon 1 stays normal. Xenon 2's external button cycles normal, invalid-type, 20 Hz flood, and 4 Hz anomaly. The Argon enforces rules locally; a learned statistical rate detector on the laptop can request temporary containment.

**Working software MVP, with hardware validation outstanding.** Both firmware projects are pinned to Device OS **1.5.2**. The simulator, backend, dashboard, portable C++ core, and automated tests were exercised here. The Particle CLI/ARM toolchain and physical boards were unavailable: **Particle firmware compilation, flashing, wiring, USB behavior on boards, and actual bus fault timing remain unverified**. Simulation is never a hardware test. Read [the compatibility audit](docs/COMPATIBILITY.md) before flashing.

No Particle Mesh, Wi-Fi, runtime cloud connection, user accounts, LLM, Node build, or second zone. A Particle developer account may be needed only if you choose the optional cloud compiler; local Workbench compilation avoids that dependency. Runtime stays on your laptop and boards.

## Quick start — Windows PowerShell

Install Python **3.11 or 3.12** from [python.org](https://www.python.org/downloads/windows/). Commands use an explicit virtual-environment interpreter, so you do not need to change PowerShell's execution policy. Replace the example repository location below with your actual location; it is the only placeholder in this block.

```powershell
# PLACEHOLDER: replace this path with your MeshShield repository.
Set-Location "C:\Users\YOUR_NAME\Documents\MeshShield"
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m backend --simulate
```

Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)**. The yellow **SIMULATION** badge is intentional. After one second both nodes should be HEALTHY with about one received/allowed message per second. Use the explicitly labeled simulation-only mode selector for node 2. Stop with Ctrl+C. Use `--http-port 8001` if 8000 is occupied; open the matching URL.

On macOS/Linux, from this repository:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m backend --simulate
```

The server binds to `127.0.0.1`, serves API/assets from the same origin, and starts exactly **one worker without reload**. Do not run multiple backends against one Argon. Automatic containment starts **off**. Baselines and history are in memory and reset when the backend restarts.

## Repository map

| Path | Purpose |
|---|---|
| `firmware/xenon/src/main.cpp` | Reusable standalone endpoint, bounded packet queue, debounced button |
| `firmware/xenon/src/node_config.h` | Build-time `MESH_NODE` = 1 or 2 |
| `firmware/argon/src/main.cpp` | Two-bus gateway, summaries, bounded USB logging/commands |
| `shared/protocol.h`, `shared/policy.h`, `shared/command.h` | Canonical packet codec, policy state, strict command parser |
| `scripts/sync_shared.py` | Copy headers into both independently compilable Particle projects |
| `scripts/configure_xenon.py` | Select endpoint identity/address before compilation |
| `backend/` | FastAPI service, serial owner, validated events, state, learned detector |
| `simulator/gateway.py` | Selectable fake serial/gateway using the same event/command schemas |
| `dashboard/` | Plain HTML/CSS/JavaScript; no build step or CDN |
| `tests/` | Python policy/detector/API/bridge tests and native C++ core checks |
| `docs/PROTOCOL.md` | Packet layout, CRC vectors, USB schemas, exact detector semantics |
| `docs/COMPATIBILITY.md` | Official Particle evidence, pinned APIs, timing qualifications |

## Wiring

Power off/disconnect USB while wiring. Use **3.3 V logic only**. All three boards are powered by USB. **Do not connect their regulated 3V3 outputs together.** Pull-ups on both buses connect to the **Argon's** 3V3 output. Do not leave an unpowered board attached to powered signal/pull-up lines; it can be back-powered through pins.

| Connection | Argon | Xenon 1 | Xenon 2 | Additional part |
|---|---|---|---|---|
| Bus 1 SDA | D0 (`Wire`) | D0 | — | 4.7 kΩ from SDA to Argon 3V3 |
| Bus 1 SCL | D1 (`Wire`) | D1 | — | 4.7 kΩ from SCL to Argon 3V3 |
| Bus 2 SDA | D2 (`Wire1`) | — | D0 | Separate 4.7 kΩ from SDA to Argon 3V3 |
| Bus 2 SCL | D3 (`Wire1`) | — | D1 | Separate 4.7 kΩ from SCL to Argon 3V3 |
| Common ground | GND | GND | GND | All grounds connected |
| External mode button | — | — | D4 ↔ GND | Normally open pushbutton, internal `INPUT_PULLUP` |
| Power | USB | USB | USB | Data-capable USB cables; Argon USB goes to laptop |

Node 1 is address **0x21** on Wire, node 2 **0x22** on Wire1. Both Xenons use their primary Wire port, D0/D1. Do not confuse the external mode button with Particle's onboard MODE/SETUP button. Keep wiring short. The gateway trusts physical bus mapping, not a self-reported identity.

Each node is polled roughly every **20 ms** at 100 kHz. `requestFrom` requests a 5 ms timeout, but **Device OS 1.5.2 adds about 52 ms of recovery on errors**. A failing node backs off 250 ms before its next attempt. Each loop still services the other node; this is bounded application work, not a hard real-time deadline. See the source evidence in the compatibility audit.

## Firmware compilation and USB flashing — Windows

### Recommended: pinned local Particle Workbench

Install [Particle Workbench](https://docs.particle.io/getting-started/developer-tools/workbench/) and the [Particle CLI/Windows USB drivers](https://docs.particle.io/getting-started/developer-tools/cli/) using Particle's official installers. Verify the CLI from PowerShell:

```powershell
particle --version
particle usb list
.\.venv\Scripts\python.exe scripts\sync_shared.py
New-Item -ItemType Directory -Force build | Out-Null
```

Do **not** use an unqualified `particle update` or a “latest” target on a Xenon: its maximum supported version is 1.5.2. This repository includes Workbench settings under each project's `.vscode/settings.json`; explicitly verify them in Workbench.

1. Configure node 1 from repository-root PowerShell:

   ```powershell
   .\.venv\Scripts\python.exe scripts\configure_xenon.py --node 1
   ```

2. Open the **`firmware\xenon` folder** in Workbench (not only the repository root). Run command-palette **Particle: Install Local Compiler** and select **1.5.2**, then **Particle: Configure Workspace for Device**, select **1.5.2** and **Xenon**. No device cloud name is required for USB.
3. Run **Particle: Compile application & DeviceOS (local)**. This is the required real compilation check that remains unperformed here. Initial toolchain/Device OS downloads can take several minutes.
4. Connect **only Xenon 1** over USB. Put it in DFU: hold MODE, tap RESET, continue holding MODE through magenta until **blinking yellow**, then release. Run **Particle: Flash application & Device OS (local)**. Ensure **bootloader, nRF5 SoftDevice, and system firmware** match 1.5.2; application-only flashing is insufficient for an unconfigured board with incompatible system parts. Follow Workbench's dependency/USB prompts. Particle's [standalone guidance](https://docs.particle.io/archives/xenon-standalone/) explains all three required parts.
5. Disconnect node 1, select node 2, rebuild, and flash **only Xenon 2** the same way:

   ```powershell
   .\.venv\Scripts\python.exe scripts\configure_xenon.py --node 2
   ```

   Label the boards immediately. Both use the same project, but they need different compiled binaries. Changing `node_config.h` does not change an already flashed board.
6. Open **`firmware\argon`** as a separate Workbench project. Select **Argon, Device OS 1.5.2**, then **Particle: Compile application & DeviceOS (local)**. Connect only the Argon, put it in DFU, and use **Particle: Flash application & Device OS (local)**. Verify all required system dependencies before running.

The local compiler/old system package must still be available from Particle. If it cannot be installed or a dependency cannot be resolved, stop the hardware demo and use simulation; do not substitute a modern Xenon target. No Particle cloud setup is needed on either Xenon. MANUAL mode deliberately avoids waiting for provisioning/network connection.

### Optional CLI compilation and pinned USB flashing

These are exact CLI commands from the repository root. `particle compile` uses Particle's **remote build service**, so it needs Internet and an existing developer CLI login. This does not implement cloud forwarding or accounts in MeshShield. If you want entirely local compilation, use Workbench above. Legacy build-service availability is unverified here.

```powershell
.\.venv\Scripts\python.exe scripts\sync_shared.py
New-Item -ItemType Directory -Force build | Out-Null
.\.venv\Scripts\python.exe scripts\configure_xenon.py --node 1
particle compile xenon firmware\xenon --target 1.5.2 --saveTo build\xenon-1.bin
.\.venv\Scripts\python.exe scripts\configure_xenon.py --node 2
particle compile xenon firmware\xenon --target 1.5.2 --saveTo build\xenon-2.bin
particle compile argon firmware\argon --target 1.5.2 --saveTo build\argon.bin
```

Check each command succeeds before proceeding. Connect **only the named board** and put it in blinking-yellow DFU before each matching flash command. Current CLI `--local ... --target` requests the target system dependencies as well; read the output and do not bypass unresolved dependencies:

```powershell
# Only Xenon 1 connected, in DFU:
particle flash --local build\xenon-1.bin --target 1.5.2
# Disconnect it; only Xenon 2 connected, in DFU:
particle flash --local build\xenon-2.bin --target 1.5.2
# Disconnect it; only Argon connected, in DFU:
particle flash --local build\argon.bin --target 1.5.2
```

For an older CLI that only supports application DFU flashing, **first install/verify 1.5.2 system parts with Workbench**, then the archive-documented application command is:

```powershell
# Example: only Xenon 1 connected in DFU, with 1.5.2 dependencies already installed.
particle flash --usb build\xenon-1.bin
```

This legacy command alone does not upgrade system parts. To inspect unresolved dependencies, temporarily enter listening mode (hold MODE until blinking dark blue), run `particle serial inspect`, then reset back into the application. See [official CLI documentation](https://docs.particle.io/reference/developer-tools/cli/) and the compatibility audit. The exact toolchain/USB flashing flow has not been executed in this environment.

## Start with hardware

After flashing, wire the boards as above, power all three over USB, and find the Argon's serial port:

```powershell
.\.venv\Scripts\python.exe -m backend --list-ports
```

If multiple Particle ports appear, note the list with/without the Argon's cable. Close serial monitors on the Argon: Windows generally allows one owner. Replace `COM7` below with the port that actually belongs to the Argon:

```powershell
# PLACEHOLDER: COM7 must be your Argon's COM port.
.\.venv\Scripts\python.exe -m backend --port COM7
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Confirm the **HARDWARE** badge. The simulation attack selector is hidden and its API returns 404 in hardware mode. To tune the statistical threshold, append `--z-threshold 3.0` (range 1–10). Keep one worker and no auto-reload.

The gateway reconnects to the selected port after errors; if Windows assigns a different COM port, stop and restart with the new port. Stale gateway summaries mark the gateway offline after three seconds. Each node has separate bus-response and attempted-message ages. EMPTY responses keep a connected but quiet peripheral alive without inflating received traffic.

### Expected LEDs and logs

- Xenon NORMAL: green; UNKNOWN_TYPE: amber; FLOOD: red; ANOMALY: purple. Xenon 1 stays green. Node 2's physical external button cycles those four modes in order, 35 ms debounce. Mode is printed on **that Xenon's USB serial** at 115200 on changes and about every three seconds, with node and queue-overflow count.
- Argon: teal normally, red while either node is quarantined. This is an aggregate local hint; the dashboard is authoritative per node.
- Before application takes RGB control, MANUAL can breathe white. Blinking yellow means DFU. Blinking green/dark blue unexpectedly often means the wrong app/system dependencies. Unplugged USB logging does not stop gateway enforcement.
- Argon's USB stream is machine-readable JSON; do not attach another serial terminal while the backend owns it. Xenon debug ports are separate and may be monitored at 115200 using a serial terminal. Never send manual Particle special-mode baud values.

## Two-minute demo

Begin with both nodes in NORMAL, auto containment off, and no active quarantine. The table below includes baseline training; allow extra seconds if the host is slow or any interval is rejected.

| Time | Action and expected result |
|---|---|
| 0:00–1:05 | Click **Start clean baseline**. Keep both nodes NORMAL. Explain physical bus identity and received/allowed counts while 12 clean windows per node accumulate. Baseline auto-freezes at completion; Finish refuses a short baseline. |
| 1:05–1:15 | Press node 2 once (UNKNOWN_TYPE); about three invalid messages trigger 15 s quarantine. Node 1 continues. Press again to FLOOD: blocked attempts rise, countdown keeps falling instead of extending. In simulation select the corresponding modes. |
| 1:15–1:20 | Press once to ANOMALY (4 Hz), then click node 2 **Release**. Wait for acknowledgment. Keep automatic containment off briefly. |
| 1:20–1:35 | After fresh complete windows, node 2 shows ANOMALY with observed rate and learned threshold. Fixed 5/s policy allows 4/s. |
| 1:35–1:45 | Enable **Automatic containment**. The next qualifying window requests 15 s containment: pending first, quarantined only after acknowledgment. Node 1 continues near 1/s. |
| 1:45–2:00 | Return node 2 to NORMAL, let quarantine expire or manually release, and observe recovery. Continued attacks after a manual release can trigger detection again. |

Automatic containment can instead be enabled immediately after training for a shorter demonstration. Do not call the statistical detector an LLM, a compromise probability, or authentication. The fixed policy and learned threshold are different layers. Flood is **polled application traffic**, not a radio flood.

## Tests

See [the executed validation record](docs/VALIDATION.md) for results and the hardware/toolchain limits.

Python unit tests use unittest; HTTP tests need the dev dependency file. They run entirely without boards:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\sync_shared.py --check
```

If a host C++ compiler is installed, run the portable firmware core tests (this is **not** Particle firmware compilation):

```powershell
# With MSVC's Developer PowerShell:
New-Item -ItemType Directory -Force build | Out-Null
cl /EHsc /std:c++14 tests\native.cpp /Fe:build\native-tests.exe /Fo:build\native-tests.obj
.\build\native-tests.exe
# Or with a GCC/Clang c++ command available:
c++ -std=c++11 -Wall -Wextra -pedantic tests\native.cpp -o build\native-tests.exe
.\build\native-tests.exe
```

On macOS/Linux: `c++ -std=c++11 -Wall -Wextra -pedantic tests/native.cpp -o /tmp/meshshield-native && /tmp/meshshield-native`.

Tests cover CRC/packet validation, token refill, independent-node flooding, rolling violations, quarantine expiry without extension, wraparound in the C++ policy, duplicate/ancient command IDs, bounded malformed serial framing, reconnect/retry serialization, stale gateway versus node state, clean training/held-out normal traffic, 4 Hz detection, incomplete window exclusion, pending versus acknowledged dashboard state, API validation, and hardware rejection of simulation controls. Browser checks exercise the live simulation UI; neither simulator nor native host tests prove Particle firmware compatibility.

## Recovery and limitations

| Symptom | Check / recovery |
|---|---|
| Node OFFLINE, gateway online | Common ground, correct bus/pins/address and `MESH_NODE`, four pull-ups, all boards powered. Faults are transport counts, not attack violations. |
| Both nodes claim address 0x21 | Reconfigure node 2, rebuild its binary, and reflash only node 2. |
| USB port absent/busy | Data-capable cable, Particle drivers, Device Manager, no DFU mode, close other monitors. Discover ports again; specify the Argon explicitly. |
| Invalid/malformed serial lines | Wrong port, another app printing on Argon, partial connection frame, old firmware protocol. Backend discards through newline and reports diagnostics. |
| No learned baseline | Both nodes must be NORMAL; require twelve clean measured windows each. Any fault/quarantine/overflow/gap discards the open window. Check rejected-interval counters. |
| Containment pending/failed | Wait for ack; bridge retries the same ID up to three sends. At five seconds it reports unknown outcome. Check USB and next authoritative summary; a missing ack does not prove no action. |
| Release followed by another quarantine | Attack is still active. Return to NORMAL. Release does not disable fixed rules or the learned detector. |
| Unexpected Particle breathing/blinking state | Verify app target and bootloader/SoftDevice/system dependencies against 1.5.2. Do not try Wi-Fi/mesh provisioning as a workaround. |

This is a four-hour-scope demonstration, not a production security boundary. Device OS 1.5.2/Xenon are obsolete. It does not authenticate endpoints, encrypt I²C, detect replay, withstand arbitrary electrical denial of service, or infer compromise. It handles one laptop and exactly two physically mapped nodes; local-process access can issue commands. No durable storage, multi-user access, failover, or production deployment is included. The detector requires operator-controlled clean training and can miss attacks at normal rates. USB loss drops some events; visible totals cannot include missed summaries. Physical bus recovery and OS/driver scheduling can exceed nominal timing. Conduct real firmware builds and bench validation before relying on hardware behavior.
