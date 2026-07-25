**PRODUCT REQUIREMENTS DOCUMENT**

**Perception Agent & Reasoning Eval Pipeline**

Scene Validation for Photos and Video Clips — Development Phase

Document ID: PRD-PVE-001

Version 1.0  |  Status: Draft for Review

Author: Jean M. Delphonse  |  July 25, 2026

# **Table of Contents**

# **1\. Document Control**

| Field | Value |
| :---- | :---- |
| Document ID | PRD-PVE-001 |
| Version | 1.0 (Draft) |
| Author / Owner | Jean M. Delphonse |
| Phase | Development (pre-launch iteration); production monitoring is out of scope for v1.0 |
| Related documents | PRD-SIM-PAA-001 (Physical Action Agents) — shared perception concepts; independent codebase |
| Configuration note | All numeric thresholds, confidence bands, rubric versions, and sampling rates referenced in this PRD are admin-configurable (Admin → Eval Configuration). No threshold value in this document is to be hardcoded. |

# **2\. Executive Summary**

This PRD defines a new context application composed of two coupled systems. The first is a Perception Agent that views photos and video clips and validates the objects, people, and content present in specific scenes — producing not only verdicts but fully structured reasoning traces. The second is a Reasoning Eval Pipeline that evaluates the quality of the agent's thinking during development: not merely whether the agent reached the right answer, but whether it detected accurately, applied the correct context, calibrated its confidence honestly, and communicated usefully.

The development-phase posture optimizes for diagnostic depth and iteration speed over throughput and cost. The central artifact is a closed loop: change the agent (prompt, model, sampling strategy) → run the eval suite → compare per-dimension deltas against the prior run → inspect regressions in a failure gallery → form a hypothesis → change again. Every component in this document exists to serve that loop.

Architecture follows the established stack: Flask / SQLAlchemy / MySQL, Claude vision API for the Perception Agent and a pinned second Claude instance as LLM judge, 9-character alphanumeric primary keys via generate\_pk(), and a Flask-served failure gallery as the primary debugging surface.

# **3\. Goals & Non-Goals**

## **3.1 Goals**

* Enable an agent to ingest photos and video clips and validate objects, people, and scene content against optional validation targets (expectations, policies, or open questions).

* Require the agent to expose a structured reasoning trace — detections, context applied, alternatives considered, verdict, and confidence — so that reasoning itself is evaluable.

* Build a versioned, reproducible eval pipeline scoring four independent dimensions: perceptual accuracy, contextual reasoning quality, calibration, and feedback quality.

* Ship a failure gallery UI that makes every failure diagnosable in under two minutes of human inspection.

* Keep a full eval run under 30 minutes and a smoke-set run under 5 minutes so the loop is executed multiple times per day.

## **3.2 Non-Goals (v1.0)**

* Production traffic monitoring, drift alarms, and sampled spot-checks (deferred; dev rubrics graduate into monitors in a later phase).

* Real-time streaming perception. v1.0 is batch: uploaded photos and clips.

* Identity recognition of specific known individuals. v1.0 detects and describes people generically; identity resolution is a privacy-sensitive extension deferred by design.

* Training or fine-tuning vision models. The agent is prompt- and orchestration-engineered on hosted models.

* Single blended quality score. Per-dimension scores are never collapsed during development.

# **4\. Users & Use Context**

The users of this system in the development phase are the builders themselves. There are three working roles, which may be held by the same person:

| Role | Needs | Primary surface |
| :---- | :---- | :---- |
| Agent Engineer | Fast iteration on prompts/orchestration; per-dimension deltas between runs; reproducibility | CLI eval runner \+ run comparison view |
| Eval Curator | Add/label scenes, write reasoning keys, tag failure diagnoses, audit the judge | Failure gallery \+ scene admin |
| Reviewer / Stakeholder | Milestone-level progress: calibration curves, dimension trends across runs | Eval dashboard |

# **5\. System Architecture Overview**

The pipeline runs left to right: Ingestion (upload or REST API) → Frame Sampler (scene-change detection for clips) → Perception Agent (Claude vision, structured JSON out) → Results Store (MySQL) → Eval Runner (deterministic scorers \+ LLM judge, batch) → Eval Dashboard & Failure Gallery (Flask views).

## **5.1 Components**

| Component | Responsibility | Technology |
| :---- | :---- | :---- |
| Ingestion Service | Accept photos (JPEG/PNG) and clips (MP4, ≤ admin-configured max duration); store media; create Scene records | Flask endpoint \+ object storage path convention |
| Frame Sampler | Extract keyframes from clips via scene-change detection; fall back to fixed-rate sampling (rate admin-configurable) | PySceneDetect \+ ffmpeg |
| Perception Agent | Detection → Contextualization → Feedback; emits structured reasoning trace per Section 6 | Claude vision API (model string stored per run) |
| Results Store | Persist agent outputs, eval scores, run metadata with full config hashes | MySQL via SQLAlchemy; 9-char alphanumeric PKs (generate\_pk()) |
| Eval Runner | Batch job: deterministic detection scoring, LLM-judge reasoning scoring, calibration computation | Python batch worker (APScheduler acceptable for v1.0) |
| Failure Gallery / Dashboard | Browse failures with full trace vs. ground truth; run comparisons; calibration report | Flask \+ Jinja templates |

## **5.2 Two-agent separation**

The Perception Agent and the LLM judge are strictly separated. The judge receives the ground-truth answer key and the versioned rubric; the agent never does. The judge's model version is pinned per rubric version — it does not float — so that score movement is attributable to agent changes, not judge drift.

# **6\. Perception Agent — Functional Requirements**

## **6.1 The claim model**

Every perception job carries an optional validation target, because open-ended description and targeted validation exercise different reasoning. Three target types are supported in v1.0:

* **Expectation —** A stated expectation the scene should satisfy, e.g., "this clip should show a delivery at the front door — does it?"

* **Policy —** A rule the scene is checked against, e.g., "no unknown persons in restricted areas."

* **Open question —** No target; the agent describes and categorizes what it observes.

## **6.2 Output contract**

The agent must return a single JSON object per scene (per keyframe set for clips, plus a temporal synthesis). The reasoning trace is mandatory — a verdict without a trace is a contract violation and fails the run. Canonical shape:

{

  "detections": \[{"entity": "knife", "bbox": \[...\], "confidence": 0.94}\],

  "context\_applied": \["location: hallway", "time: 02:00", "no residents expected awake"\],

  "reasoning": "Knife detected outside expected zones; hallway at 2am elevates anomaly score",

  "alternatives\_considered": \["dropped kitchen item", "reflection / false positive"\],

  "verdict": {"category": "anomaly", "confidence": 0.78, "action\_hint": "escalate"},

  "feedback\_text": "A knife appears in the hallway, which is unusual for this time and location.",

  "temporal\_summary": null

}

## **6.3 Requirements**

| ID | Requirement | Priority |
| :---- | :---- | :---- |
| PVE-101 | Agent accepts photo or sampled clip frames plus optional validation target and scene metadata (location label, timestamp, prior-frame summaries). | P0 |
| PVE-102 | Agent output conforms to the Section 6.2 JSON contract; schema-validated on receipt; nonconforming output recorded as a contract failure, not silently repaired. | P0 |
| PVE-103 | Detection stage enumerates objects, people (generic), scene type, visible text, and — for clips — actions. | P0 |
| PVE-104 | Contextualization stage must cite each context factor it used; citing context not supplied in the input is recorded as hallucinated context. | P0 |
| PVE-105 | Verdict includes category, confidence in \[0,1\], and action\_hint drawn from a configured vocabulary (Admin → Eval Configuration). | P0 |
| PVE-106 | For ambiguous inputs, the agent may return category "uncertain" with a list of information that would resolve the ambiguity; this is a first-class success path, not a fallback. | P0 |
| PVE-107 | For clips, a temporal\_summary synthesizes entities, actions, and timeline across keyframes ("what happened," not just "what is present"). | P1 |
| PVE-108 | Frame sampling uses scene-change detection with a fixed-rate fallback; the agent may request additional frames up to an admin-configured budget (optimal-stopping behavior is itself evaluated — see PVE-312). | P1 |
| PVE-109 | Every agent invocation stores prompt version, model string, sampling config, and input hashes for reproducibility. | P0 |

# **7\. Eval Dataset — Scenes, Tiers, and Reasoning Keys**

## **7.1 Starting composition (\~50 scenes)**

The dataset starts deliberately small and grows from observed failures rather than imagination. Initial distribution:

| Tier | Count | Purpose | Example |
| :---- | :---- | :---- | :---- |
| Easy (regression canaries) | \~20 | Clear objects, unambiguous context; any failure signals a fundamental break | Coffee mug on desk, daytime |
| Adversarial (context-flip pairs) | \~15 | Same object, paired scenes, opposite correct verdicts; a failure isolates the ignored contextual signal | Knife/kitchen vs. knife/hallway; person/front-door-day vs. person/window-2am |
| Ambiguous | \~10 | Correct answer is low confidence plus a request for resolving information; tests epistemic honesty | Partially occluded object; unclear intent |
| Temporal (clips) | \~5 | Meaning emerges only across frames | Picking up a package vs. taking one — identical single frames |

## **7.2 Ground-truth record and reasoning key**

Each scene stores: entities present, correct context factors, expected verdict, an expected confidence band (e.g., 0.4–0.7 for genuinely ambiguous scenes — bands configured per scene, not hardcoded), and a reasoning key. The reasoning key lists the two to three things a good trace must mention and anything it must not hallucinate. The reasoning key is what converts LLM-judge scoring from vibes into a checkable rubric.

## **7.3 Growth policy (explore/exploit)**

* **Exploit —** Every diagnosed real failure becomes a new scene plus two to three generated variants of it.

* **Explore —** A small weekly quota of novel scene types is added regardless of failure history, to keep the set from narrowing around known weaknesses.

* **Rotation —** Scenes referenced in agent prompt iterations are flagged; if smoke-set scores climb while fresh-scene scores stagnate, the affected scenes rotate out of scored runs (leakage control).

## **7.4 Requirements**

| ID | Requirement | Priority |
| :---- | :---- | :---- |
| PVE-201 | Scene records include tier, media reference, ground truth, reasoning key, expected confidence band, and dataset version tag. | P0 |
| PVE-202 | Adversarial scenes are stored as linked pairs so pair-level failures are reportable as such. | P0 |
| PVE-203 | Scene admin UI supports create, label, pair-link, retire/rotate, and version-tag operations. | P1 |
| PVE-204 | Dataset versions are immutable once referenced by a run; edits create a new version. | P0 |

# **8\. Eval Pipeline — Scoring, Judge, and Runs**

## **8.1 Four independent dimensions**

| Dimension | What it measures | Scoring method |
| :---- | :---- | :---- |
| Perceptual accuracy | Did the agent detect what is actually there? | Deterministic: precision/recall vs. labeled entities |
| Contextual reasoning | Did it apply the right context and avoid hallucinating context? | LLM judge vs. reasoning key, anchored rubric |
| Calibration | Does stated confidence match empirical accuracy? | Deterministic: bucketed confidence vs. accuracy; per-band checks against expected bands |
| Feedback quality | Is the plain-language output accurate, appropriately hedged, useful? | LLM judge, anchored rubric |

Dimensions are reported separately and never collapsed into one number during development. The run-comparison view is a per-dimension delta table between run N and run N−1, with drill-down to the specific scenes that flipped.

## **8.2 LLM judge design**

* The judge receives the reasoning key, ground truth, and a versioned rubric with explicit score anchors (e.g., 3 \= applied all required context factors; 2 \= some; 1 \= none or hallucinated context).

* The judge must output which required factor was missed; those strings accumulate into the failure taxonomy automatically.

* Judge audit: on a configured cadence, a human scores \~20 judged traces independently and agreement is computed; agreement below the configured floor blocks rubric promotion.

* Judge model version is pinned per rubric version; rubric and judge upgrade together, never silently.

## **8.3 Run mechanics**

| ID | Requirement | Priority |
| :---- | :---- | :---- |
| PVE-301 | Every run stores: agent config hash, prompt version, agent model string, judge model string, rubric version, dataset version, and timestamps. Runs are reproducible from stored config. | P0 |
| PVE-302 | Smoke set (\~30 canonical scenes) completes in under 5 minutes; full suite in under 30 minutes (targets admin-configurable). | P0 |
| PVE-303 | Deterministic scorers run before the judge; contract failures (PVE-102) short-circuit judge spend on that scene. | P0 |
| PVE-304 | Calibration report: predictions bucketed by stated confidence with accuracy per bucket, rendered as a curve; flatness (all predictions in a narrow high band) is flagged explicitly. | P0 |
| PVE-305 | Run comparison view: per-dimension deltas vs. any prior run, with pass→fail and fail→pass scene lists. | P0 |
| PVE-306 | Hallucinated-context detections (PVE-104) are surfaced as their own count per run. | P0 |
| PVE-311 | Judge agreement audit workflow per Section 8.2, with results stored per rubric version. | P1 |
| PVE-312 | For clips, the eval scores frame-sampling efficiency: did the agent stop requesting frames at the right time (optimal stopping), measured against per-scene sufficient-frame annotations. | P2 |

# **9\. Failure Gallery & Dashboard**

The failure gallery is the primary product of the development phase: a Flask view that makes every failure diagnosable side by side. Each card shows the frame or clip, ground truth and reasoning key, the agent's full JSON trace, and the judge's score with its stated reason.

| ID | Requirement | Priority |
| :---- | :---- | :---- |
| PVE-401 | Filter by run, dimension, score range, tier, and failure-taxonomy tag. | P0 |
| PVE-402 | Free-text diagnosis field per failure (e.g., "ignored timestamp," "hallucinated a person," "right verdict, fabricated reasoning"); diagnoses are queryable and frequency-countable. | P0 |
| PVE-403 | Adversarial pairs render together with a pair-level pass/fail badge. | P1 |
| PVE-404 | Dashboard: dimension trends across runs, calibration curve, current failure-taxonomy frequency table. | P1 |
| PVE-405 | One-click "promote failure to scene": creates a new scene record pre-filled from the failed case (feeds Section 7.3 exploit path). | P1 |

# **10\. Data Model (MySQL)**

All tables use 9-character alphanumeric primary keys via generate\_pk(), consistent with platform convention. Core tables:

| Table | Key fields |
| :---- | :---- |
| scenes | pk, tier, media\_path, media\_type, pair\_pk (nullable), ground\_truth\_json, reasoning\_key\_json, expected\_conf\_low, expected\_conf\_high, dataset\_version, status |
| runs | pk, agent\_config\_hash, prompt\_version, agent\_model, judge\_model, rubric\_version, dataset\_version, started\_at, finished\_at, run\_type (smoke|full) |
| agent\_results | pk, run\_pk, scene\_pk, output\_json, contract\_valid, hallucinated\_context\_count, created\_at |
| eval\_scores | pk, agent\_result\_pk, dimension, score, judge\_reason, missed\_factors\_json |
| diagnoses | pk, agent\_result\_pk, tag, note, author, created\_at |
| rubrics | pk, version, dimension, rubric\_json, judge\_model, human\_agreement, status |
| config | pk, key, value\_json — Admin → Eval Configuration store (thresholds, bands, budgets, cadences) |

# **11\. REST API (v1.0)**

| Endpoint | Method | Purpose |
| :---- | :---- | :---- |
| /api/v1/scenes | POST / GET | Create scene with media upload; list/filter scenes |
| /api/v1/scenes/\<pk\> | GET / PATCH | Retrieve or update (new dataset version on edit per PVE-204) |
| /api/v1/runs | POST / GET | Launch smoke or full run; list runs |
| /api/v1/runs/\<pk\>/compare/\<other\_pk\> | GET | Per-dimension delta payload |
| /api/v1/runs/\<pk\>/calibration | GET | Bucketed calibration data |
| /api/v1/results/\<pk\>/diagnose | POST | Attach diagnosis tag/note |
| /api/v1/results/\<pk\>/promote | POST | Promote failure to new scene (PVE-405) |

# **12\. Algorithms to Live By — Design Lenses Applied**

| Lens | Application in this system |
| :---- | :---- |
| Optimal Stopping (37% rule) | Frame sampling: the agent's decision of when to stop requesting frames is itself a scored thinking skill (PVE-312). Also applied to labeling effort — stop curating the initial set at \~50 scenes and let failures drive growth. |
| Explore vs. Exploit | Dataset growth policy (Section 7.3): exploit known failure modes with variants; reserve a weekly explore quota for novel scene types. |
| Bayesian Updating | Contextual-reasoning rubric is framed as: did the agent update its prior correctly given the context evidence? This makes dimension 2 principled rather than impressionistic. |
| Caching | Recognized-entity and prior-frame summaries are supplied as context so repeat sightings are cheap; deterministic scorer results are cached per (scene, agent output) pair. |
| Scheduling (Shortest Job First) | Smoke set before full suite; deterministic scorers before judge spend (PVE-303); the sub-5-minute smoke run keeps the human loop tight. |
| Overfitting | Leakage control via scene rotation (Section 7.3); the single-score prohibition; the warning that rising smoke scores with flat fresh-scene scores means the eval — not the agent — has been optimized. |
| Relaxation | A crude eval run daily beats a perfect one run monthly: Week 1 ships a closed loop with deterministic scoring only, judge and gallery follow. |

# **13\. Milestones & Sequencing**

| Week | Deliverable | Exit criterion |
| :---- | :---- | :---- |
| Week 1 | 20 easy \+ 10 adversarial scenes; ingestion; agent with output contract; deterministic detection scoring; results in MySQL; CLI runner | Loop closed end to end; smoke run \< 5 min |
| Week 2 | LLM judge with reasoning keys and anchored rubric; ambiguous tier; failure gallery with diagnosis field | First judged run; 10 failures diagnosed |
| Week 3 | Temporal clips \+ frame sampler; calibration report; run-comparison view; promote-to-scene | Full suite \< 30 min; first calibration curve reviewed |
| Week 4+ | Judge agreement audit; taxonomy frequency dashboard; scene rotation; explore quota in place | Rubric v2 promoted only after agreement floor met |

# **14\. Success Metrics (Development Phase)**

* Loop velocity: ≥ 3 eval runs per working day sustained across a two-week window.

* Diagnosability: median time from opening a failure card to writing a diagnosis under 2 minutes.

* Adversarial pair pass rate trending upward across runs without easy-tier regression.

* Calibration: agent's confidence distribution is non-flat, and per-bucket accuracy deviation shrinks run over run (targets in Admin → Eval Configuration).

* Judge trustworthiness: human–judge agreement at or above the configured floor for every promoted rubric version.

* Dataset health: ≥ 50% of net-new scenes originate from promoted real failures by Week 4\.

# **15\. Risks & Open Questions**

| Risk / Question | Mitigation / Owner note |
| :---- | :---- |
| Judge leniency or drift silently corrupts scores | Pinned judge model per rubric version; recurring human agreement audit (PVE-311) gates rubric promotion |
| Eval-set leakage into agent prompting inflates scores | Scene flagging and rotation; fresh-scene tracking; overfitting alarm in dashboard |
| Reasoning traces are post-hoc rationalizations rather than faithful thinking | Adversarial pairs and hallucinated-context detection partially expose this; note as a known epistemic limit of trace-based evaluation |
| People-related scenes raise privacy concerns even without identity resolution | v1.0 uses staged/consented media only for people scenes; identity features remain out of scope until a dedicated privacy review |
| Open: single canonical agent prompt vs. per-target-type prompts (expectation / policy / open)? | Decide by end of Week 2 based on failure taxonomy evidence |
| Open: does the eval later graduate into production monitoring as one codebase or a fork? | Design run/rubric tables to be reusable; defer decision |

