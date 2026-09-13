# Send-message demo

This adds a real message relay alongside the original virtual-device experiment. Your partner opens an inbox on their laptop; you and the judges open the sender page on the same Wi-Fi or hotspot. The Argon stays connected to the host laptop by USB. No Xenon or Argon Wi-Fi setup is needed.

## What the demo enforces

The backend provisions a fresh 128-bit sender code over trusted USB. Every submitted UTF-8 message (at most 160 bytes) and sender code is sent to the Argon. The Argon compares the code and evaluates its own message policy. It returns a correlated decision. Only a matching `allowed` response puts that exact pending message in the inbox. Missing responses, disconnects and timeouts do not deliver messages. Messages are never automatically retried.

Approved code holders share message slot 1. Missing or wrong codes share slot 2. Each slot has capacity 5, refill 5/second, and 15-second quarantine after three violations within ten seconds. Unauthorized attempts do not consume the approved slot's bucket. These two message slots are independent of the original virtual traffic and its learned detector. The LED is red when any virtual or message slot is quarantined.

This is a shared bearer-code demo, not cryptographic laptop identity or Windows ping filtering. Anyone with the approved code can send. The trusted backend provisions the code and hosts the inbox; it is part of the trust boundary. The Argon receives the text but does not scan its meaning. HTTP is unencrypted; use disposable codes/text on a trusted demo network. All unapproved judges share one quarantine, intentionally. The inbox code grants read access only; it does not authorize sending.

## Prepare firmware

Stop any running backend before flashing. The old firmware continues to run the original demo but does not support message delivery; the new page will remain not ready until the new firmware is installed.

```powershell
Set-Location 'C:\Users\lyben\OneDrive\Documents\GitHub\MeshShield'
.\.venv\Scripts\python.exe scripts\sync_shared.py
New-Item -ItemType Directory -Force build | Out-Null
& "$env:LOCALAPPDATA\particle\bin\particle.exe" compile argon firmware\argon --target 1.5.2 --saveTo build\argon-messages.bin
& "$env:LOCALAPPDATA\particle\bin\particle.exe" flash --local --target 1.5.2 build\argon-messages.bin
```

The compile command uploads source to Particle. Use the existing Workbench instructions in the README if compiling locally instead. Retain the proven 1.5.2 target. For DFU drivers or failed system dependencies, follow the README's recovery steps.

## Start and share

1. Connect all demo laptops to the same Wi-Fi/hotspot. Some guest networks isolate clients; use a hotspot allowing client-to-client access if the page cannot be reached.
2. Run `ipconfig` on the USB-host laptop. Find its active Wi-Fi adapter's IPv4 address. The example below uses **192.168.1.20**; replace it with the actual address.
3. Discover the Argon port and start one backend:

```powershell
.\.venv\Scripts\python.exe -m backend --list-ports
.\.venv\Scripts\python.exe -m backend --port COM4 --lan-host 192.168.1.20
```

4. On the host laptop open **http://127.0.0.1:8000/messages**. This local page shows the operator panel with the share URL and two codes. The original dashboard remains at **http://127.0.0.1:8000/**.
5. Your partner and judges open the displayed share URL, for example **http://192.168.1.20:8000/messages**. Do not give them a localhost URL. No Python installation is needed on their laptops.
6. Give your partner the **inbox code**, enter it in the inbox form and click Open inbox. Give only the approved sender the **sender code**. Judges can leave the sender code blank or enter a wrong code.

If Windows Firewall prompts, allow the Python backend on the trusted private demo network only. No firewall rules are created automatically. The LAN option listens on all IPv4 interfaces; use it only during the demo. The application accepts the configured LAN Host header and keeps management endpoints restricted to actual loopback connections, ignoring forwarded-IP headers. Only message pages/assets, readiness, submission and code-protected inbox access are available remotely.

Without `--lan-host`, the backend stays localhost-only. For a software preview use `--simulate` instead of `--port COM4`; the page explicitly displays FULL SOFTWARE SIMULATION.

## Presentation sequence

1. Approved sender enters their code and sends "Hello from our team". Show the Argon allow result and the text appearing in your partner's inbox.
2. A judge sends without the code. Show `unauthorized` and no new inbox entry.
3. Repeat three unauthorized attempts within ten seconds. Show quarantine and the red LED.
4. While judges' slot is quarantined, send another approved message: it still arrives.
5. Wait fifteen seconds. The next wrong-code attempt is unauthorized again; quarantine drops do not prolong the expiry.

Sending many approved messages can rate-limit and quarantine the approved slot too. The learned anomaly demonstration remains on the original virtual-device dashboard; irregular human typing is not used to train that detector.

## Restart and limits

If the hotspot reassigns your IP while the LAN-enabled backend is still running, open `http://127.0.0.1:8000/messages` on the host laptop. Under Operator setup, enter the new Wi-Fi IPv4 address and click **Update address**. This changes the accepted LAN address and share URL without resetting codes, the inbox or the gateway. Give your partner the new URL. The old URL is no longer accepted. The field does not assign an address to Windows or enable a localhost-only listener; start with `--lan-host` first. Updates are in memory, so after a backend restart use the current address in the startup command again.

Ctrl+C stops the backend. Restart with the same command, checking the current COM port and LAN address if they changed. Codes and inbox history reset on backend restart. Share the new codes. Only the latest 50 approved texts and 50 decision records are kept in memory, and at most 16 messages can await gateway decisions. An HTTP error can occur after a successful delivery, so check the inbox before manually sending again. This is a demo relay, not a durable messenger or protection against network-level denial of service.

The backend does not reflash or reconfigure your board automatically. Existing physical validation in VALIDATION.md applies to the original virtual-device demo; the new relay requires its own flash and two-laptop test.
