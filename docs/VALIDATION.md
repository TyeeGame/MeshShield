# Validation in this checkout

Executed September 12, 2026 (local time), on branch `argon-only-migration`.

- 26 Python unittest tests passed, with no skips, using the project's Python 3.12 virtual environment. Coverage includes traffic modes, handshake gating, reconnect handshake invalidation, independent devices, quarantine expiry without extension, duplicate commands, learned containment, baseline restart and HTTP behavior.
- Node dashboard stalled-request/offline and retry regression passed.
- Shared-header synchronization check and packaging unittest passed.
- `git diff --check` passed.
- Particle CLI 3.50.1 is installed at `%LOCALAPPDATA%\particle\bin\particle.exe`; Workbench extension 1.16.50 is installed, but no local toolchains directory/compiler was found.
- Particle USB discovery reported `No devices found`; backend port discovery returned no ports. No board was flashed or physically tested.
- After explicit user authorization, Particle cloud compilation succeeded for Argon Device OS 1.5.2. Output: `build/argon.bin`; reported application usage: 9,752 bytes flash and 11,360 bytes RAM. The binary is ignored by Git.
- Portable native C++ tests were not run: no host C++ compiler was found on PATH. Python policy tests do not replace those tests or a Particle build.

Still required: flash matching system/application firmware and test USB traffic, measured modes, isolation, expiry, learned containment and disconnect/reconnect on a real Argon. Firmware compilation is verified; physical operation is not.

Migration used only the compatibility-checked patch, against commit `77aeaf20189d97b7fa2bd0fdc67087d7e636bacb`. The ZIP inventory was inspected but not extracted. Original project and Git history were preserved; changes remain uncommitted. Patch, ZIP, virtual environment and build output are ignored.
