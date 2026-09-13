# MeshShield

MeshShield is an application-message security demo built with one Particle Argon, a Python backend, and a browser dashboard.

In the message demo, laptops on the same Wi-Fi or hotspot send short messages through the backend to the USB-connected Argon. The Argon checks a shared sender code, limits message rates, and temporarily quarantines repeated violations. The backend adds a message to the partner inbox only after receiving a matching allow decision from the Argon.

The project also includes two laptop-generated virtual devices for demonstrating packet validation, flood protection, and learned statistical anomaly detection. The detector learns normal traffic rates on the laptop and can request containment; the Argon enforces it.

- **Hardware:** one Argon and a USB data cable; no Xenon or external sensors.
- **Interface:** plain HTML, CSS, and JavaScript; no frontend build step.
- **Scope:** protects this message service, not all Wi-Fi traffic or Windows ping. Shared codes do not authenticate physical laptops. The demo uses unencrypted HTTP on a trusted network.
- **Simulation:** a separate, clearly labeled software mode works without a board.

See [setup and flashing](docs/SETUP.md), [the message-demo guide](docs/MESSAGE-DEMO.md), and [validation results](docs/VALIDATION.md).
