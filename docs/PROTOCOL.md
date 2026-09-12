# MeshShield protocols

## Endpoint packet, version 1

Exactly **18 bytes**, at most one per gateway poll, unsigned little-endian unless specified. Canonical C++ encoder: `shared/protocol.h`; Python equivalent: `backend/protocol.py`. `scripts/sync_shared.py` copies canonical headers into each Particle project's `src`; committed copies make projects self-contained for Particle upload/local builds. `--check` fails on drift.

| Offset | Bytes | Field |
|---|---:|---|
| 0 | 1 | Protocol version, 1 |
| 1 | 1 | Type: 0 EMPTY, 1 TELEMETRY; 127 used for UNKNOWN_TYPE demo |
| 2 | 4 | Endpoint sequence, incremented for each generated message, wraps mod 2³² |
| 6 | 4 | Endpoint uptime, milliseconds mod 2³² |
| 10 | 2 | Signed int16 simulated temperature in hundredths of a degree (2200 = 22.00); no physical sensor required |
| 12 | 4 | Endpoint cumulative outgoing queue overflow count; reset on endpoint restart |
| 16 | 2 | CRC-16/CCITT-FALSE over bytes 0–15; little-endian CRC storage |

CRC parameters: polynomial 0x1021, initial value 0xFFFF, input/output unreflected, xorout 0. Standard check: ASCII `123456789` → **0x29B1**. Full packet test vector (type=1, sequence=1, uptime=1000, sensor=2200, overflow=0):

```text
01 01 01 00 00 00 e8 03 00 00 98 08 00 00 00 00 54 1e
```

Never transmit a raw C++ struct. CRC detects accidental corruption; it provides **no authentication**, replay resistance, or protection against a peripheral intentionally forging values. Bus 0/address 0x21 means node 1; bus 1/address 0x22 means node 2. Packets do not carry trusted names or node identities.

EMPTY is CRC/version-validated, carries the latest prepared uptime/overflow/sequence, and is not counted as received/allowed/blocked telemetry. It proves a peripheral answered even if it had nothing queued. A malformed attempted EMPTY is a malformed application packet. Zero bytes returned by I²C is a transport fault; short nonzero responses are malformed packets. Quarantined traffic remains polled and counted, but valid EMPTY remains separate. Queue overflow counts messages lost before polling; policy blocked counts messages the gateway actually received and rejected.

Rule order: length → CRC → version → type → token bucket. At most one triggering violation per nonempty packet. During quarantine nonempty packets count under `quarantine`, without extending its timer or creating violations. Capacity 5/refill 5 per second; three violations younger than 10,000 ms trigger 15,000 ms quarantine. Exactly 10,000 ms old violations expire. On release/expiry, clear violations and refill the bucket. Wrap-safe unsigned elapsed times handle gateway `millis()` rollover. EMPTY and transport errors never trigger policy quarantine.

Xenon has eight queued packets. Main loop prepares/copies packets under short interrupt masking; callback pops/copies without logging or allocation. Sequence gaps and overflow expose loss; the protocol does not implement retransmission. Normal scheduling is 1000 ±40 ms, UNKNOWN_TYPE the same, FLOOD 50 ms, ANOMALY 250 ms. Button is D4 with INPUT_PULLUP and 35 ms stable debounce. This is a **polled application-message flood**, not a radio flood.

## Gateway → laptop: newline-delimited JSON

USB CDC, **115200**, UTF-8 ASCII-compatible JSON, LF termination. Maximum event including LF **1536 bytes**; maximum command including LF **256 bytes**. No baud values such as 1200 or 14400 that invoke Particle special modes. No waiting for USB connection, no `flush`. Parser drops an oversized line through LF and resumes. Malformed/unsupported events are counted and invalidate the current detector window; they never crash the bridge. No raw input is inserted as HTML.

Every event has:

```json
{"v":1,"session":1234,"seq":42,"type":"..."}
```

`session`: nonzero random uint32 for gateway boot. `seq`: uint32 incremented on every attempted event, including dropped events. A gap invalidates open detector windows. Event sequence rollover requires a gateway restart in this MVP (roughly years at normal demo rates); endpoint sequences and policy clocks may wrap independently. Backend ignores out-of-order/duplicate events and resynchronizes new sessions from a summary. Baselines are kept in process memory across a gateway reconnect; partial windows/streaks reset. Backend restart clears learned baselines.

### Summary (once per second)

```json
{
  "v":1,"session":1234,"seq":42,"type":"summary",
  "duration_ms":1002,"uptime_ms":51002,"log_drops":0,"last_command_id":4,
  "nodes":[
    {"node":1,"received":1,"allowed":1,"blocked":0,"transport":0,"empty":49,
     "queue_overflow":0,"quarantine_ms":0,"contaminated":false,
     "seen_age_ms":2,"message_age_ms":600,
     "reasons":{"malformed":0,"checksum":0,"version":0,"unknown_type":0,"rate_limit":0,"quarantine":0}},
    {"node":2,"received":4,"allowed":4,"blocked":0,"transport":0,"empty":46,
     "queue_overflow":0,"quarantine_ms":0,"contaminated":false,
     "seen_age_ms":2,"message_age_ms":100,
     "reasons":{"malformed":0,"checksum":0,"version":0,"unknown_type":0,"rate_limit":0,"quarantine":0}}
  ]
}
```

Counts/reasons are **interval deltas**, reset after every attempted summary; `duration_ms` is actual elapsed gateway observation time, not assumed 1000 ms. `received = allowed + blocked`; sum of reasons = blocked. `transport`, `empty`, `queue_overflow` are separate. `log_drops` is a cumulative counter for frames not queued; a missing frame causes an event-sequence gap. Backend totals cover received summaries since connection/session synchronization, **not** traffic it never observed.

`seen_age_ms`: age of most recent nonzero peripheral response (including EMPTY); `message_age_ms`: most recent nonempty attempted packet; -1 means never. Gateway connectivity and peripheral freshness are independent. Node becomes offline after 2.5 seconds without a recent bus response; gateway summary becomes stale at 3 seconds. Message freshness is displayed separately even if EMPTY responses keep the bus alive.

`quarantine_ms`: authoritative remaining duration at emission; backend uses monotonic countdown between events. `contaminated`: any quarantine during interval, or observed endpoint uptime reset. Preserves quarantine-spanning-window invalidation even when quarantine expires before the summary.

### Sampled telemetry and incidents

```json
{"v":1,"session":1234,"seq":43,"type":"telemetry","node":1,"packet_seq":50,"uptime_ms":51000,"sensor":2200}
{"v":1,"session":1234,"seq":44,"type":"incident","node":2,"reason":"rate_limit"}
{"v":1,"session":1234,"seq":45,"type":"error","reason":"malformed_command"}
```

Accepted telemetry: at most one sample per node per second; summary retains all allowed counts. Incidents: at most three per node per summary interval; summary retains all block reasons. Error reasons: `malformed_command`, `command_too_long`. Firmware TX has six 1536-byte slots. A full/disconnected sink drops new frames; partially sent frames are never overwritten. Loop sends at most 128 bytes where `availableForWrite` reports space. Disconnect discards pending TX frames. Dropped acknowledgments can be recovered by idempotent command retry. Enforcement runs regardless of logging throughput.

## Laptop → gateway commands

Exactly these five keys, any order. Unsigned integers, case-sensitive plain ASCII operation string, no escapes, arrays, floats, signed numbers, duplicate or extra keys. ID and session are nonzero uint32.

```json
{"session":1234,"id":5,"op":"quarantine","node":2,"duration_ms":15000}
{"session":1234,"id":6,"op":"release","node":2,"duration_ms":0}
{"session":1234,"id":7,"op":"state","node":2,"duration_ms":0}
```

Allowed nodes 1/2. Quarantine duration 1–60000 ms (out of range rejected, never silently extended); release/state require zero. `state` makes no changes and returns current node quarantine state in ack; full traffic state follows in the next summary. Commands never travel through Xenon packets.

IDs must increase across all nodes **within the gateway session**. Summary's `last_command_id` lets a restarted backend resume numbering. Gateway remembers the last 16 applied command bodies: exact retry returns `ok` and current remaining quarantine without reapplying; reused ID with different content returns `id_conflict`. Older IDs outside the cache return `stale_id` without execution. A high-water mark prevents very old retries extending quarantine despite bounded memory. One laptop owner is assumed. At ID exhaustion restart the gateway.

### Acknowledgment, emitted after application

```json
{"v":1,"session":1234,"seq":46,"type":"ack","id":5,"node":2,"status":"ok","duplicate":false,"quarantine_ms":15000,"last_command_id":5}
```

Statuses: `ok`, `wrong_session`, `invalid_command`, `id_conflict`, `stale_id`. `quarantine_ms` is **current** state, including for duplicates. Backend keeps at most one outstanding command per node and therefore at most two queued writes. Bridge is the sole write owner, has a 200 ms hardware write timeout, retries the same payload after one second (at most three sends), and marks an unacknowledged command failed/unknown after five seconds or disconnect. A partial write is a transport failure.

Dashboard shows **CONTAINMENT PENDING** for a pending quarantine request, even if a summary arrives before its ack. It shows **QUARANTINED** after a matching successful ack, or an authoritative summary for autonomous policy containment with no pending request. A failed command does not imply that hardware did nothing: later summaries can reveal its actual state. Manual release does not disable detection/automatic containment; continued attack can cause another quarantine.

## Learned detector

User triggers training while both nodes are NORMAL. Discard the first summary crossing that trigger. Build nonoverlapping windows by accumulating consecutive complete summaries until at least **5000 measured ms**; close at that summary boundary, never split/estimate packet counts across a summary. Healthy hardware windows are approximately five seconds (e.g. 5005 ms); this small boundary overrun is deliberately included in the rate denominator. A training run takes twelve clean windows per node, **at least 60 seconds** plus initial alignment, and longer after rejected windows. No unfinished window is ever learned. Finish refuses insufficient samples; baseline auto-freezes once both nodes have 12 windows.

Training clean guards: no blocks, quarantine, transport faults, overflow, serial gaps, stale peripherals, or pending commands; summary durations must be 800–1500 ms. A clean-mode training window must have 0.4–1.6 messages/s. These are demo-specific guards, not proof that a device is uncompromised. The operator must keep both nodes NORMAL: a subtle or mixed attack may still resemble normal traffic. Changing simulator modes during training also invalidates the current window in the API. Do not train on known attack data.

For each node, learn arithmetic mean rate and sample standard deviation; use **sigma=max(sample SD, 0.25 msg/s)**. Freeze after training. Threshold = mean + z × sigma, default z=3; configure with `--z-threshold`. Require two consecutive complete above-threshold windows. Normal ~1 Hz typically yields threshold 1.75 Hz; ANOMALY ~4 Hz is above this and below fixed 5 Hz sustained gateway policy. Alert displays observed rate, baseline, threshold, reason, and standardized deviation in API; it is not a probability of compromise. Automatic containment is off by default, optional, and sends 15 seconds only after confirmed anomaly. Disabling it does not cancel a command already sent.

Incomplete/gapped/disconnected/quarantine/blocked/overflow windows reset the open window and anomaly streak. After recovery the detector needs fresh complete windows. Learned baseline survives short gateway disconnections but not backend restart; retrain if device identity/configuration changes. No model, metrics, incidents, or commands are persisted to disk in this MVP.
