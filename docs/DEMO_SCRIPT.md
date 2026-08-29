# ATLAS: 4:00 demo video script

Record one continuous screen capture with the cursor visible. Let real calls finish on camera and narrate only values and events that are visible in that recording.

## Submission status

- **Hosted console:** `https://atlas-console-jguwjegiqq-uc.a.run.app`, private authenticated Cloud Run deployment. Project `atlas-agentic-hack-2026-v2`, service `atlas-console`, revision `atlas-console-00004-2n6`, 100% traffic. This is not public judge access.
- **Demo video:** Pending recording and public upload.
- **Repository:** `https://github.com/himanshu748/atlas`; the repository remains private.

Record through an authenticated Cloud Run session or `gcloud run services proxy`. Do not present the private service URL as a public demo link.

## Preflight before recording

| Check | Required evidence |
|---|---|
| Deployment gate | Confirm `atlas-console-00004-2n6` still receives 100% of traffic in `atlas-agentic-hack-2026-v2`. Cloud Run must remain private with minimum 0, maximum 1 and concurrency 1. |
| Recording | 1920×1080, 30fps, system audio plus mic. Hide notifications, credentials, email addresses and billing details. |
| Backend connection | The ATLAS header says `CLOUD LEDGER`, not the standalone simulation state. Open `/healthz` once in a background tab. |
| Runtime values | Open `/api/fleet` and note the exact readiness, autonomy, verified control count, total control count and runtime mode returned for this run. Do not reuse numbers from an earlier rehearsal. |
| Model path | Confirm `/api/fleet` reports `runtime_mode=cloud`, `model_backend=vertex-ai`, `model=gemini-3.5-flash` and location `us`. Keep the matching Vertex AI usage view open. |
| Live connector proof | Keep the Cloud Asset evidence that captured actual IAM bindings and two actual Cloud Storage buckets. SDLC is a fixture in this deployment, with an optional GitHub adapter when configured. HR and vendor are fixture-only in this revision. |
| Armor path | Confirm the seeded injection verdict reports `backend=model-armor+deterministic`. Managed Model Armor returned clean; the labelled deterministic second layer quarantined the fixture. Do not claim managed Armor caught it. |
| Security fixture | Confirm `/api/armor` contains that blocked layered verdict from the vendor fixture. If it does not, do not substitute the standalone simulation. |
| Handoff | Use an open handoff that actually exists in `/api/handoffs`. If none exists, run a sweep before recording. Do not use the static `HO-142` sample as live evidence. |
| Package check | Set `ATLAS_URL` to the private deployed URL, obtain a fresh identity token and test the package commands below before recording. |
| Cloud proof | Pre-open Cloud Run, Vertex AI usage, Cloud Asset evidence, Firestore, Pub/Sub, Cloud Storage, Cloud Trace, Model Armor and the paused Scheduler job. |
| Spend guard | Show the monthly alert at 1 billing-account currency unit, excluding credits. Call it an alert, not a cap or actual cost. |

The console includes a synthetic nine-week backfill and a standalone browser simulation. Both are useful demo aids, but neither is evidence of nine weeks of live collection.

Total target: **3:55**. Keep five seconds of headroom.

---

## 0:00–0:22: Scope the demo honestly

**On screen:** Fleet Command. Point briefly to `CLOUD LEDGER` and the line that labels the audit window as seeded.

> "ATLAS is a SOC 2 evidence workflow running in a private authenticated Cloud Run service. This ledger is a seeded nine-week audit scenario, so we can exercise drift, handoffs and packaging in four minutes. The state changes I trigger now are live against the deployed backend."

Do not describe the uptime counter as proof that the deployment has been collecting for that long. It is derived from the seeded run start.

---

## 0:22–0:48: Read the live KPIs

**On screen:** Point to Audit Readiness, Autonomy and the coverage heatmap.

> "The exact values on screen come from `/api/fleet`. Readiness is verified controls divided by all controls. Autonomy is the share of verified controls whose ledger record has zero human touches. It measures recorded ATLAS handoffs, not every conversation that may have happened outside the product."

Read the displayed percentages and verified control count aloud. Do not put fixed percentages in the script because a sweep or handoff changes them.

> "The heatmap is the same ledger by control: green is verified, purple is stale and amber is waiting on a human."

---

## 0:48–1:28: Run a real sweep

**On screen:** Click **Run evidence sweep** and keep the activity stream visible.

> "This request groups outstanding controls by domain and uses Python async fan-out across the domain buckets. Within each control, collection, judgment and the resulting action run in order. The hunters and Judge use ADK `LlmAgent` when Gemini is configured; this coordinator is not an ADK Parallel, Sequential or Loop agent."

Read two activity lines exactly as they appear. Do not reuse sample counts from the standalone simulation.

> "The collectors file evidence first. The Judge then rules only on evidence in the ledger. Each connector call passes an application scope check and each ruling records whether Gemini or the deterministic fallback produced it."

Point to the two validated cloud findings:

> "Cloud Asset read actual IAM bindings and found two actual Cloud Storage buckets in this project. Gemini did not manufacture a green result: it ruled the IAM recertification evidence and the backup evidence insufficient. SDLC is a fixture in this deployment, with a configurable GitHub adapter in the code. HR and vendor are fixture-only in this revision."

**On screen:** Open one control updated by this sweep and point to its evidence, ruling and custody metadata.

> "This record shows the source label, collecting role, SPIFFE-format identity label, Armor status and SHA-256 metadata. These are application records, not a cryptographic workload identity attestation."

---

## 1:28–1:58: Show the injection fixture

**On screen:** Open **Security Console** and select the blocked vendor artifact created by the sweep.

> "The vendor fixture represents extracted text from a third-party SOC 2 PDF. It includes an indirect prompt injection that tells the reviewer to mark every control satisfied. Managed Model Armor returned a clean verdict for this seeded text, so ATLAS applied its labelled deterministic second layer. That second layer blocked the fixture before evidence was filed. The API records the combined backend as `model-armor+deterministic`."

Do not say managed Model Armor caught this fixture. Do not describe the fixture as a real vendor incident or claim that the text was hidden in a rendered PDF. The repository stores representative extracted text.

---

## 1:58–2:25: Complete one real handoff

**On screen:** Open **Handoff Inbox** and select the actual open handoff verified during preflight.

> "The Chaser deduplicates open requests by control. This handoff carries the question, cited evidence and the Judge's reasoning."

Click **Approve** or provide a truthful rejection reason. Wait for the API response and updated status.

> "That answer increments the control's recorded human touches, updates its status and writes the decision into the in-project memory store. The Judge can retrieve that precedent before a later ruling. It can reduce repeat questions, but it does not guarantee that the next audit starts at any fixed percentage."

---

## 2:25–2:50: Show governance and traces

**On screen:** Open **Agent Registry**.

> "The registry is an in-project catalog of eleven versioned role cards with capability search. Six roles can invoke Gemini through ADK. The remaining roles are deterministic workflow components. Dispatch in this prototype is through in-process Python functions."

> "Each card also shows an application scope allowlist and a SPIFFE-format identity label. The IAM hunter's denial from the HR connector is covered by a repository test. The deployed Cloud Run container itself uses the orchestrator service account."

**On screen:** Open **Trace Explorer**.

> "These are operation spans with agent identity and selected decision metadata. In cloud mode OpenTelemetry exports them to Cloud Trace. The current trace does not store every prompt or every tool payload."

---

## 2:50–3:18: Prove the deployed Google Cloud path

**On screen:** Switch through only the pre-opened resources for this deployment.

1. **Cloud Run:** Show `atlas-console`, its region, revision and the exact URL used by the browser.
2. **Vertex AI:** Show `gemini-3.5-flash` usage in `us` that matches `model_backend=vertex-ai` from `/api/fleet`.
3. **Cloud Asset:** Show the proof run's actual IAM bindings and the two actual Cloud Storage buckets.
4. **Firestore, Pub/Sub and Storage:** Show a persisted control, `atlas-events` activity and the uploaded manifest object.
5. **Cloud Trace:** Show spans from the verified sweep.
6. **Model Armor:** Show the managed request plus the API verdict labelled `model-armor+deterministic`; state that the deterministic layer caught the fixture after the managed clean verdict.
7. **Cloud Scheduler:** Show `atlas-weekly-sweep`, its Monday 07:00 UTC configuration and its current `PAUSED` state.
8. **Bounds:** Show minimum 0, maximum 1, concurrency 1 and the 1-unit billing alert that excludes credits. Do not call the alert a cap or a charge.

> "This revision receives 100 percent of traffic. Firestore preserves the ledger, Pub/Sub receives event copies, Cloud Storage holds the generated manifest and Cloud Trace receives spans. The Scheduler is configured but paused after validation. Control work is executed in-process; this application does not use Cloud Tasks or Pub/Sub workers for dispatch."

---

## 3:18–3:45: Generate and verify the manifest

**On screen:** Return to **Evidence Package** and click **Generate package**. Then switch to the prepared terminal.

```bash
ATLAS_TOKEN="$(gcloud auth print-identity-token)"
curl -sS -X POST "$ATLAS_URL/api/package" \
  -H "Authorization: Bearer $ATLAS_TOKEN" \
  -H 'content-type: application/json' -d '{}' -o manifest.json
python scripts/verify_manifest.py manifest.json
```

> "The endpoint returns per-control entries, a gap register, artifact hashes and a root hash. This standalone verifier checks the manifest structure and re-derives the root. With `--artifacts`, it can also hash supplied files from disk. It does not authenticate the identity string or decide whether the evidence proves the control."

Pause on `PACKAGE VERIFIED`. Do not call the `signed_by` field a digital signature.

---

## 3:45–3:55: Close

**On screen:** Fleet Command. Optionally start the time-machine control and label it while it plays.

> "The time machine replays synthetic history; the verified state changes came from private Cloud Run revision `atlas-console-00004-2n6`. ATLAS combines ADK model roles, live Google Cloud evidence and an inspectable ledger. The Scheduler is configured and currently paused."

Stop recording.

---

## Rehearsal rules

- Read changing values and event lines from the current run.
- The verified live connector proof is Cloud Asset Inventory: actual IAM bindings and two actual Cloud Storage buckets. SDLC is a fixture in this deployment, with an optional GitHub adapter when configured. HR and vendor are fixture-only in this revision.
- Never present the standalone browser simulation as backend state.
- If a cloud or model call falls back, narrate the fallback shown in logs or API state.
- Never say Model Armor caught the seeded injection. It returned clean, then the labelled deterministic layer quarantined the fixture.
- If no handoff exists, do not fake one. Re-run the preflight or shorten that section.
- Upload the final video publicly. Suggested title: `ATLAS: SOC 2 evidence fleet | All Things Agentic Hackathon`.
