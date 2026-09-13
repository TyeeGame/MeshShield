# Dashboard appearance

Both views share `dashboard/theme.css`. Inter is bundled as a local variable WOFF2 font with its SIL Open Font License in `dashboard/fonts/`. The browser needs no connection to a font provider. The LAN route allowlist permits this font and the shared stylesheet while keeping operator APIs local-only.

The palette comes from [the selected Coolors palette](https://coolors.co/palette/0d1b2a-1b263b-415a77-778da9-e0e1dd):

| Color | Use |
|---|---|
| `#0d1b2a` | Page, inputs and chart background |
| `#1b263b` | Panels and secondary controls |
| `#415a77` | Borders, dividers and chart grid |
| `#778da9` | Secondary accents, placeholders and focus outlines |
| `#e0e1dd` | Main text and neutral primary buttons |

Green remains healthy/allowed, yellow means warning/pending, and red means quarantine/blocked or failed delivery. Status text accompanies the colors. Rate graph strokes follow the current endpoint state; they do not label the severity of each historical sample.

Headings describe the view or action: Traffic overview, Anomaly detection, Messages, Send a message, and Message inbox. No lab branding or marketing slogans are used. Virtual endpoints remain explicitly labeled as simulated, and hardware/simulation mode labels remain visible.

Validation: 36 Python tests passed, including LAN font/theme access and operator-access isolation. The dashboard timeout/retry check, message JavaScript syntax check and whitespace check passed. Both pages were visually inspected in a browser using the simulator, including the healthy and pending graph colors. These are UI checks; no firmware changes were made. Restart an already-running backend once to load the new LAN asset allowlist, then refresh the pages. No Argon flash is required.
