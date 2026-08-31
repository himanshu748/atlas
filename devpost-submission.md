# Title

ATLAS: Autonomous Assurance Fleet

## One-line Summary

Eleven governed workflow roles collect live cloud evidence, judge SOC 2 controls and ship a hash-verifiable audit package.

## Problem

SOC 2 preparation is a long, repetitive workflow. Compliance teams collect screenshots and exports, chase owners, decide whether evidence is sufficient and rebuild the same context next year. Evidence can go stale while the audit is still in progress.

## Solution

ATLAS models this work as eleven registered workflow roles. Five domain hunters collect evidence, a separate Control Judge evaluates that evidence with Gemini 3.5 Flash and deterministic components manage handoffs, drift, packaging and redaction. Firestore keeps durable state, Pub/Sub receives event copies, Cloud Trace records spans and Cloud Run provides a private scale-to-zero runtime.

The deployed proof read real IAM bindings and two real Cloud Storage buckets through Cloud Asset Inventory. Gemini correctly ruled that the data was insufficient to prove quarterly recertification or recovery testing instead of manufacturing a green result.

## Why This Matters

ATLAS reduces high-volume audit preparation while keeping the consequential judgment inspectable. Every filed record carries source, collector identity, screening state and a SHA-256 hash. Human involvement is measured rather than hidden, and the independent manifest verifier re-derives internal hashes and reports evidence gaps. The root hash binds artifact hashes with each control's ID, status, verdict and human-touch count, so changing a verdict breaks verification.

## How We Used AI

- Gemini 3.5 Flash runs through Vertex AI and Google ADK `LlmAgent` roles.
- Evidence hunters summarize what each artifact proves or fails to prove.
- The Control Judge returns structured `SATISFIED`, `INSUFFICIENT` or `NEEDS_HUMAN` rulings with cited evidence.
- Memory is recalled before judgment so prior human requirements affect later decisions.
- Managed Model Armor screens untrusted content. After a managed clean verdict, a labelled deterministic guard still checks high-signal injection patterns. The seeded fixture was caught by that second layer and recorded as `model-armor+deterministic`.

## How We Used Codex

Codex helped turn the initial prototype into a deployable product. It audited product claims against the implementation, hardened the Google Cloud scripts, added project and spend boundaries, fixed Firestore key handling, implemented live Cloud Asset reads, added tests, verified the manifest, inspected desktop and mobile rendering and validated the deployed Cloud Run revision. Codex also caught an important security truth: managed Model Armor returned clean for the seeded injection, so the final product records and explains the deterministic second-layer detection instead of overstating the managed service.

## Key Features

- Eleven registered workflow roles with scoped application identities
- Five evidence domains with live GCP IAM and infrastructure reads in the deployed proof
- Separate evidence collection and control judgment
- Persistent Firestore ledger, memory, handoffs and idempotent task keys
- Human escalation inbox and measurable autonomy
- Managed Model Armor plus a labelled deterministic second layer
- OpenTelemetry traces exported to Cloud Trace
- Verifiable manifest with per-artifact hashes, a root hash binding every control verdict, and a gap register
- Private Cloud Run deployment with scale-to-zero and a paused Scheduler job

## Architecture

One FastAPI container serves the console, API and SSE stream on private Cloud Run. Python async control flow coordinates the role sequence in-process. Gemini 3.5 Flash is accessed through Vertex AI in `us`. Firestore stores durable application state, Pub/Sub receives event copies, Cloud Storage stores generated manifests and Cloud Trace receives OpenTelemetry spans. Cloud Scheduler is provisioned for recurring sweeps but intentionally paused for cost control.

Architecture diagram: `docs/architecture.png`

## Testing Instructions

Public repository: https://github.com/himanshu748/atlas

```bash
git clone https://github.com/himanshu748/atlas
cd atlas
pip install -r requirements.txt
pytest -q
uvicorn app.main:app --port 8080
```

Open http://localhost:8080. Local mode needs no Google Cloud credentials and uses an in-memory ledger, clearly labelled fixtures and a deterministic reasoning fallback. The current repository test suite passes without cloud credentials.

The verified workflow deployment is private Cloud Run service `atlas-console`, revision `atlas-console-00004-2n6`, in project `atlas-agentic-hack-2026-v2`. A separate public Cloud Run service provides a safe read-only console where every control has a visible, model-labelled ruling: 62 seeded deterministic decisions plus two sanitised rulings captured from the verified private Gemini run. The public runtime makes no live model calls and has no direct project IAM role bindings.

## Public Demo Link

Public judge console: https://atlas-public-demo-jguwjegiqq-uc.a.run.app

Private workflow proof URL: https://atlas-console-jguwjegiqq-uc.a.run.app

## Public Repository Link

https://github.com/himanshu748/atlas

## Devpost Project

https://devpost.com/software/atlas-autonomous-assurance-fleet

The project page and hackathon entry are live. The public video, architecture diagram and project thumbnail are attached. Devpost verified the final entry on August 29, 2026.

## Demo Video

Public video: https://www.youtube.com/watch?v=ZbEzvKVPXIU

Title: **ATLAS: Autonomous Assurance Fleet | All Things Agentic Hackathon**

Runtime: **2:00**. Public playback was verified.

The final cut covers:

1. Open immediately on the working Fleet Command screen and state the problem.
2. Trigger or inspect the live evidence flow and show real IAM and Cloud Asset evidence.
3. Show Gemini's honest `INSUFFICIENT` ruling and the human-handoff boundary.
4. Show the layered prompt-injection quarantine with truthful backend provenance.
5. Generate and independently verify the manifest.
6. End on Cloud Run revision, Vertex AI activity, Cloud Trace spans and the paused Scheduler.

Final timestamped run sheet: `docs/DEMO_SCRIPT.md`

## Screenshot Shot List

1. Fleet Command with readiness, autonomy, control coverage and live activity.
2. Control detail showing a real `gcp.iam` or `gcp.asset` record plus Gemini's cited ruling.
3. Security Console showing the blocked fixture and `model-armor+deterministic` provenance.
4. Evidence Package screen with the generated root hash and gap register.
5. Google Cloud Console showing Cloud Run revision `atlas-console-00004-2n6` and 100 percent traffic.

## Submission Readiness Notes

- [x] Registered for the All Things Agentic Hackathon
- [x] Project was built during the official submission period
- [x] Category selected: Fortified Enterprise Fleet
- [x] Gemini 3.5 Flash or newer
- [x] Google Agent Framework: Agent Development Kit
- [x] Google Cloud infrastructure: Cloud Run, Firestore, Pub/Sub, Cloud Storage and Cloud Trace
- [x] Public repository with reproducible README instructions
- [x] Anonymous clean-clone test passed
- [x] Architecture diagram exists
- [x] Private Google Cloud deployment proof exists
- [x] Architecture diagram uploaded to the Devpost file field
- [x] Public demo video uploaded to YouTube
- [x] Public playback verified; runtime is 2:00
- [x] Final Devpost project created or updated
- [x] Final project submitted to the hackathon

## Known Limitations

- Cloud Run is intentionally private and the Scheduler remains paused to reduce spend.
- The deployed proof uses live Cloud Asset IAM and bucket data. SDLC is a fixture in this deployment, with an optional GitHub adapter in code. HR and vendor remain fixture-only in this revision.
- Per-role SPIFFE-format identities and scopes are application controls. The Cloud Run container executes under one runtime service account.
- Managed Model Armor returned clean for the seeded injection. The labelled deterministic second layer quarantined it.
- The verifier checks manifest integrity and provenance fields, covering artifact hashes and control verdicts, but does not cryptographically authenticate package origin or bind the full natural-language ruling narrative.
- The Google Cloud budget is an alert, not a hard spending cap.

## Official Form Fields

- Submitter Type: `Individuals`
- Submitter country of residence: `India`
- Category: `Fortified Enterprise Fleet`
- Organization name: `Not applicable, individual submission`
- Project start date: `08-29-26`
- Code repository: `https://github.com/himanshu748/atlas`
- Reproducible testing instructions in README: `Yes`
- Hosted project URL: leave blank because the verified deployment is private
- Private testing instructions: `Use the public repository Quickstart for anonymous local testing. Cloud Run deployment proof is shown in the public demo video.`
- Google SDK: `Agent Development Kit (ADK)`
- Google Cloud service dropdowns: `Cloud Run`, `Firestore`, `Pub/Sub`
- Architecture diagram upload: `docs/architecture.png`
- Google AI models: `Gemini 3.5 Flash through Vertex AI`
- Startup Prize fields: leave blank unless entering on behalf of an incorporated organization
- Bonus content link: `https://www.youtube.com/watch?v=ZbEzvKVPXIU`
- Bonus social link: pending publication
- Demo video URL: `https://www.youtube.com/watch?v=ZbEzvKVPXIU`
