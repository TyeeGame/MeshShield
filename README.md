# MeshShield — one Argon, one USB cable

Two **simulated endpoints** send laptop-generated packets over USB. The real Argon validates format, CRC, version and message type, applies independent token buckets (capacity 5; refill 5/second), and quarantines a slot for 15 seconds after three violations within ten seconds. Quarantine drops do not extend expiry; release permits later detection again. Slots are host-assigned, not authenticated identities. CRC detects corruption, not forgery.

No Xenons, external wiring, buttons, sensors, Wi-Fi setup or runtime cloud forwarding. Hardware policy decisions come from the Argon. The backend waits for a fresh `usb_virtual` summary, including after reconnect, and serializes traffic and acknowledged management commands through one USB owner.

## Windows startup

For the new sender/partner-inbox experience, see [the send-message demo guide](docs/MESSAGE-DEMO.md). It requires the updated firmware and an explicit LAN startup option; the original demo below remains available.

This checkout already has a prepared `.venv`. To recreate it on this laptop, use the bundled Python below; on another computer use `py -3.12 -m venv .venv` with Python installed.

```powershell
Set-Location 'C:\Users\lyben\OneDrive\Documents\GitHub\MeshShield'
& 'C:\Users\lyben\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m backend --simulate
```

Open [the dashboard](http://127.0.0.1:8000). Simulation displays **FULL SOFTWARE SIMULATION**. Stop with Ctrl+C before starting hardware mode:

```powershell
.\.venv\Scripts\python.exe -m backend --list-ports
# Replace COM7 with the discovered Argon port.
.\.venv\Scripts\python.exe -m backend --port COM7
```

Hardware displays **ARGON HARDWARE · VIRTUAL DEVICES**. Close other serial monitors. Run one backend without reload. Add `--http-port 8001` if needed. If the COM number changes, restart with the new port.

## Compile and flash one Argon

Device OS **1.5.2** is retained; it is not an Argon hardware restriction. Particle cloud compilation succeeded for this target; the binary is `build/argon.bin`. The user completed the one-board USB demo checks described in [current validation](docs/VALIDATION.md).

1. Run `.\.venv\Scripts\python.exe scripts\sync_shared.py`.
2. Open `firmware/argon` in Particle Workbench. Use **Particle: Install Local Compiler** for 1.5.2 and **Particle: Configure Workspace for Device**, selecting Argon and 1.5.2. Leave device identity blank for USB.
3. Run **Particle: Compile application (local)**. A successful build is required before claiming firmware compatibility.
4. Connect the Argon with a data-capable Micro-USB cable. Run **Particle: Flash application & Device OS (local)** to install matching system parts. If manual DFU is needed, hold MODE, tap RESET, and release MODE when flashing yellow. Teal indicates no quarantine; red indicates quarantine.

These commands follow [Particle Workbench documentation](https://docs.particle.io/getting-started/developer-tools/workbench/). No local compiler is installed here yet. The CLI exists outside PATH:

```powershell
& "$env:LOCALAPPDATA\particle\bin\particle.exe" --version
& "$env:LOCALAPPDATA\particle\bin\particle.exe" usb list
```

Optional cloud compilation uploads firmware source to Particle and requires network access/login:

```powershell
New-Item -ItemType Directory -Force build | Out-Null
& "$env:LOCALAPPDATA\particle\bin\particle.exe" compile argon firmware\argon --target 1.5.2 --saveTo build\argon.bin
& "$env:LOCALAPPDATA\particle\bin\particle.exe" flash --local --target 1.5.2 build\argon.bin
```

### Windows driver and legacy system dependency checks

If Windows shows **Argon DFU Mode / Code 28** while the LED blinks yellow, install **WinUSB** for that exact device using Zadig, following [Particle's Windows driver guide](https://docs.particle.io/troubleshooting/guides/build-tools-troubleshooting/win10-device-drivers/). Confirm the selected device is the Argon before installing; then retry `particle usb list`. A USB data cable is required.

A successful application flash alone did not complete system setup on the tested board. It stayed blinking blue with the gateway offline. With the backend stopped and the board in listening mode, inspect dependencies:

```powershell
& "$env:LOCALAPPDATA\particle\bin\particle.exe" serial identify
& "$env:LOCALAPPDATA\particle\bin\particle.exe" serial inspect
```

The observed system version was 1.5.2 (1512), but its dependency check failed: radio stack **202** was required and **169** was installed. Put the board into flashing-yellow DFU mode (hold MODE, tap RESET, release MODE when yellow), then run:

```powershell
& "$env:LOCALAPPDATA\particle\bin\particle.exe" update --target 1.5.2
```

Keep USB connected until completion. This update resolved the observed failure and the application started with a steady teal LED. Use the explicit target, not an unqualified update. See [Particle's update reference](https://docs.particle.io/reference/developer-tools/cli/#particle-update).

For an unconfigured board running Device OS 3.x or earlier, `particle usb setup-done` sets the persistent setup flag over USB; do not use `--reset`, which clears it. This does not provision Wi-Fi. Setting that flag and stopping listening mode did **not** fix the radio-stack mismatch on the tested board; inspect dependencies if blue blinking persists. After startup, discover the serial port again and start hardware mode (COM4 was used in this test).

## Demo

Device 1 stays near 1 valid packet/second. The device 2 selector works in hardware and simulation:

| Mode | Target | Expected behavior |
|---|---|---|
| NORMAL | 1 valid/second | Allowed |
| UNKNOWN_TYPE | 1 unknown type/second | Blocked, then quarantine |
| FLOOD | 20 valid/second | Rate limiting, then quarantine |
| ANOMALY | 4 valid/second | Learned detector can flag the increase |

Use the dashboard's Argon-measured rates; host scheduling may reduce targets. Verify device 1 continues while device 2 is quarantined. Return to NORMAL before release to avoid immediate renewed violations.

Automatic containment starts **off**. With both slots NORMAL and healthy, start a clean baseline: twelve complete five-second windows per device, at least sixty seconds. It freezes automatically. Incomplete, disconnected, blocked and quarantine-contaminated windows are excluded. Enable automatic containment and select ANOMALY: two consecutive high-rate windows request quarantine, which remains pending until acknowledgment. This is learned statistical anomaly detection, not an LLM or a probability of compromise. Baselines/history reset when the backend restarts.

If training stalls, inspect rejected intervals and log drops. Missing ports suggest cable/driver issues or DFU mode; busy ports suggest another serial owner. Wrong firmware requires flashing the USB-only project.

## Checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\sync_shared.py --check
& 'C:\Users\lyben\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' tests/test_dashboard.js
```

Canonical headers are in `shared/`; the sole firmware project is `firmware/argon`. The plain dashboard needs no frontend build. [Protocol](docs/PROTOCOL.md) describes the 18-byte packet and separate JSON commands. Simulator and fake-serial tests are not hardware validation.
