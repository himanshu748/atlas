# Asset Descriptions

The automated recapture was rate-limited, so no assets from the blocked recapture path are used. Every image below was manually inspected, cropped to remove account details and registered through media-use.

- `.media/images/image_001.png` — verified ATLAS Google Cloud architecture diagram from `docs/architecture.png`.
- `.media/images/image_002.png` — authenticated Google Cloud Scheduler view showing `atlas-weekly-sweep` in `Paused` state at `0 7 * * 1` UTC.
- `.media/images/image_003.png` — authenticated Cloud Run revision view showing `atlas-console-00004-2n6` receiving 100% of traffic.
- `.media/images/image_004.png` — authenticated Google Cloud Trace view showing real Gemini, memory recall and Control Judge spans.
- `.media/images/image_005.png` — authenticated Cloud Run revision settings showing concurrency 1, revision maximum 1 and `GOOGLE_GENAI_USE_VERTEXAI=true`.
- `.media/images/image_006.png` — live ATLAS Cloud Ledger Fleet Command cropped before the changing application budget estimate. It shows 3% readiness, 100% autonomy and 2 of 64 controls verified.
- The ATLAS palette and typography in `tokens.json` come from the shipped `web/static/styles.css`.

Exact durable proof used in motion frames:

- Control `A1.3`, source `gcp.asset`, artifact `a1-3-cloud-asset-buckets-2026-08-29.json`, 436 bytes, Armor `pass`, Gemini verdict `INSUFFICIENT`.
- Control `CC6.105`, source `gcp.iam`, artifact `cc6-105-iam-bindings-2026-08-29.json`, 9,275 bytes, Armor `pass`, Gemini verdict `INSUFFICIENT`.
- Stored package `atlas-soc2-2026-run-2026-q3`, 28 artifacts, 2 of 64 verified, 62 gaps and root hash `661c7cb1fca893712a52b4c84b2eaa6070a09d45738e2f3de6651ca63f128055`.
- The independent verifier re-derived the root hash and returned `PACKAGE VERIFIED`.
