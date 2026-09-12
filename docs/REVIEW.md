# Argon-only revision

Based on upstream 77aeaf20189d97b7fa2bd0fdc67087d7e636bacb. Local changes, not pushed to GitHub. Replaces Xenon/I2C ingress with bounded USB packet ingress; adds laptop traffic generation with fair per-device scheduling and no catch-up bursts; checks firmware handshake; exposes the mode selector in hardware; retains gateway policy and acknowledgment semantics. Removes Xenon projects/configuration and obsolete wiring guide. Includes prior training-restart and dashboard timeout fixes. See README for setup and VALIDATION.md for limits.

The full patch targets original upstream, not the earlier review patch. Preserve local work, then use git apply --check with the patch's actual path before applying. Do not overwrite a teammate's newer checkout wholesale.
