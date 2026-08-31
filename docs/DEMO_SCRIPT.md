# ATLAS: final 2:00 demo video

## Published video

- **Title:** ATLAS: Autonomous Assurance Fleet | All Things Agentic Hackathon
- **Public URL:** https://www.youtube.com/watch?v=ZbEzvKVPXIU
- **Runtime:** 2:00
- **Playback:** Public playback verified
- **Narration:** Deepgram Aura-2

The final video is a concise judge-facing proof film assembled from captures of the authenticated ATLAS deployment and its Google Cloud resources. The workflow service remains private. Judges can also use the separate read-only console at https://atlas-public-demo-jguwjegiqq-uc.a.run.app, which exposes labelled fixtures and recorded Gemini proof without production access.

## Final run of show

| Time | Proof beat |
|---|---|
| 0:00–0:04 | Establish the standard: collect evidence without inventing assurance. |
| 0:04–0:13 | Introduce the eleven-role governed fleet and verifiable package. |
| 0:13–0:21 | Show the deployed Cloud Ledger at 2 of 64 controls verified and 3% ready. |
| 0:21–0:35 | Show the real Cloud Asset Inventory record for two Cloud Storage buckets and its custody metadata. |
| 0:35–0:45 | Show Gemini 3.5 Flash ruling the recovery-testing evidence `INSUFFICIENT`, with `A1.3 NOT MET`. |
| 0:45–0:57 | Explain collection, screening, judgment, memory and packaging roles. |
| 0:57–1:09 | Show the seeded injection fixture, managed Model Armor's clean verdict and the deterministic second-layer quarantine. |
| 1:09–1:18 | Show 28 packaged artifacts, 62 declared gaps, artifact hashes and the Assembler identity label. |
| 1:18–1:27 | Show the standalone verifier returning `PACKAGE VERIFIED`. |
| 1:27–1:38 | Show the active Cloud Run revision, Vertex AI runtime proof and Cloud Trace spans. |
| 1:38–1:51 | Show scale-to-zero, the one-instance cap, concurrency one and the paused weekly sweep. |
| 1:51–2:00 | Close on trustworthy evidence, visible gaps, verifiable claims and the public GitHub repository. |

## Final narration

### 0:00–0:04: Assurance without fiction

> An audit agent should collect evidence. It should never invent assurance.

### 0:04–0:13: Meet ATLAS

> ATLAS is a governed SOC 2 assurance fleet: eleven specialized agents gather proof, judge it and assemble a package an auditor can verify.

### 0:13–0:21: The deployed ledger

> This is the deployed Cloud Ledger, not a green-screen demo. It shows the uncomfortable truth: two of sixty-four controls verified, three percent ready.

### 0:21–0:35: Evidence with custody

> For recovery testing, ATLAS queried real Cloud Asset Inventory and found the two buckets in this project. The record keeps the collector identity, source, byte count, Armor result and SHA-256.

### 0:35–0:45: Insufficient means insufficient

> But a bucket list is not proof of recovery testing. Gemini 3.5 Flash ruled the evidence insufficient, so ATLAS reported A1.3 as not met instead of manufacturing a pass.

### 0:45–0:57: A governed fleet

> That judgment sits inside a governed fleet: hunters collect, Armor screens, the Control Judge evaluates, Memory recalls policy and the Assembler packages receipts.

### 0:57–1:09: Layered defense, stated honestly

> Security is layered and explicit. Managed Model Armor returned clean on this seeded injection fixture. ATLAS's labelled deterministic layer still quarantined it and stored the combined verdict.

### 1:09–1:18: The package shows the gaps

> The durable package contains twenty-eight artifacts and sixty-two declared gaps. It also contains a root hash for every artifact and records the Assembler's SPIFFE-format identity.

### 1:18–1:27: Independent verification

> A standalone verifier imports nothing from the application. It checks manifest integrity, screening fields and identity attribution, then returns package verified.

### 1:27–1:38: Google Cloud proof

> The cloud proof is visible too: the active Cloud Run revision receives one hundred percent of traffic, Vertex AI is enabled and Cloud Trace records Gemini, memory recall and Control Judge spans.

### 1:38–1:51: Cost controls

> For the submission, cost controls stay on. Cloud Run scales to zero, the revision caps at one instance with concurrency one and the weekly sweep is paused.

### 1:51–2:00: Close

> ATLAS does not promise a perfect audit. It promises evidence you can trust, gaps you can see and claims you can verify. The code is public on GitHub.

## Claim guardrails preserved in the final cut

- The 3% readiness value and 2 of 64 verified controls come from the captured deployed Cloud Ledger. They are presented as an honest baseline, not as a success-rate claim.
- The verified live connector proof is Cloud Asset Inventory reading actual IAM bindings and two actual Cloud Storage buckets. SDLC, HR and vendor remain fixtures in this deployment.
- Gemini ruled the bucket inventory insufficient for recovery testing. The final frame says `A1.3 NOT MET`.
- Managed Model Armor returned clean for the seeded injection. The labelled deterministic second layer quarantined it. The video does not claim that managed Armor caught the fixture.
- Per-role SPIFFE-format identities are application labels, not cryptographic workload identity attestations.
- The standalone verifier checks package integrity and provenance fields. It does not decide whether evidence satisfies a control or authenticate the identity label.
- Cloud Run revision `atlas-console-00004-2n6` receives 100% of traffic. The deployment stays private with minimum zero, maximum one and concurrency one.
- The recurring Scheduler job remains paused after validation.

## Devpost status

- `docs/architecture.png` is attached to the Devpost entry.
- The hackathon entry is submitted with the hosted public judge URL.
