# Review log fixture redaction

The eight password payloads on original lines 464, 473, 481, 556, 592, 601, 669 and 670 were replaced with `<redacted>`. Each matched a Board test fixture; no production credential classification or scanner exemption was added. All other bytes and the original review verdict are retained.

Original SHA256: b2e8c4f4b88549a39cb5db192b0f288f47b4db9fb88ec5a7c5be6a6bbae6cafd
Sanitized SHA256: 0fb40d4bda80fd1254c91c51666ee5fb5e421b6180e65d18439e0e22ebe66945

The original parity receipt hash is retained when it refers to a different artifact. A review transcript and the actual parity log are separate evidence.
