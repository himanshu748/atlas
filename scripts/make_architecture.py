"""Render docs/architecture.png in the ATLAS design language."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import matplotlib.pyplot as plt

BG      = "#08090B"
PANEL   = "#101215"
RAISED  = "#171A1F"
BORDER  = "#232830"
BORDERS = "#333A45"
HI      = "#E8EAED"
MID     = "#9BA3AE"
LO      = "#616872"
GREEN   = "#3DDC97"
BLUE    = "#5B8DEF"
AMBER   = "#FFB020"
VIOLET  = "#C77DFF"
PINK    = "#FF3D71"
CYAN    = "#8FD9FF"

MONO = "DejaVu Sans Mono"
SANS = "DejaVu Sans"

fig, ax = plt.subplots(figsize=(16, 11.4), dpi=170)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 160)
ax.set_ylim(0, 114)
ax.axis("off")


def box(x, y, w, h, *, fill=PANEL, edge=BORDER, lw=1.0, r=1.4, z=2, alpha=1.0):
    p = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={r}",
        facecolor=fill, edgecolor=edge, linewidth=lw, zorder=z, alpha=alpha,
    )
    ax.add_patch(p)
    return p


def label(x, y, s, *, size=8.5, color=HI, font=SANS, weight="normal", ha="center", va="center", z=5):
    ax.text(x, y, s, fontsize=size, color=color, family=font, fontweight=weight,
            ha=ha, va=va, zorder=z)


def accent(x, y, h, color):
    """2px left status border: the design system's core structural device."""
    ax.add_patch(FancyBboxPatch((x, y), 0.32, h, boxstyle="round,pad=0,rounding_size=0.16",
                                facecolor=color, edgecolor="none", zorder=4))


def arrow(x1, y1, x2, y2, *, color=BORDERS, lw=1.1, style="-|>", rad=0.0, z=1, ls="-"):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2), arrowstyle=style, mutation_scale=9,
        color=color, linewidth=lw, zorder=z, linestyle=ls,
        connectionstyle=f"arc3,rad={rad}", shrinkA=1, shrinkB=1,
    ))


def node(x, y, w, h, title, subtitle="", *, color=BLUE, fill=PANEL, tsize=8.6, ssize=7.0):
    box(x, y, w, h, fill=fill)
    accent(x + 0.5, y + 0.7, h - 1.4, color)
    if subtitle:
        label(x + w / 2 + 0.4, y + h * 0.62, title, size=tsize, color=HI, weight="medium")
        label(x + w / 2 + 0.4, y + h * 0.28, subtitle, size=ssize, color=LO, font=MONO)
    else:
        label(x + w / 2 + 0.4, y + h / 2, title, size=tsize, color=HI, weight="medium")


# ══════════════════════════════════════════════════════ title
label(4, 109.6, "ATLAS", size=19, color=HI, font=SANS, weight="bold", ha="left")
label(20.5, 109.4, "Autonomous Assurance Fleet", size=11, color=MID, ha="left")
label(4, 105.6, "ADK LlmAgent roles  ·  async coordinator  ·  Cloud Run  ·  Firestore  ·  Pub/Sub  ·  Model Armor  ·  Cloud Trace",
      size=8, color=LO, font=MONO, ha="left")
ax.plot([4, 156], [103.2, 103.2], color=BORDER, lw=1, zorder=1)

# ══════════════════════════════════════════════════════ 1. actors
label(4, 99.6, "ACTORS", size=7.4, color=LO, font=MONO, ha="left")
node(4, 92.6, 22, 5.8, "Priya · Compliance", "reads posture, answers handoffs", color=GREEN, tsize=8.2, ssize=6.4)
node(28, 92.6, 22, 5.8, "Alex · Auditor", "verifies chain of custody", color=CYAN, tsize=8.2, ssize=6.4)
node(52, 92.6, 22, 5.8, "Dev · Engineer", "one open handoff per control", color=AMBER, tsize=8.2, ssize=6.4)

# ══════════════════════════════════════════════════════ 2. console
box(4, 82.0, 70, 8.2, fill=PANEL, edge=BORDERS)
accent(4.5, 82.7, 6.8, GREEN)
label(7.4, 87.2, "ATLAS Console", size=9.6, color=HI, weight="medium", ha="left")
label(7.4, 84.1, "FastAPI + HTML/native CSS  ·  SSE live stream  ·  private Cloud Run service",
      size=7.2, color=LO, font=MONO, ha="left")
label(71.6, 86.0, "one container", size=6.8, color=GREEN, font=MONO, ha="right")

for x in (15, 39, 63):
    arrow(x, 92.6, x, 90.4, color=BORDERS)

# right column: cross-department discovery
box(80, 82.0, 76, 16.4, fill=PANEL, edge=BORDER)
label(83, 95.6, "AGENT REGISTRY", size=7.4, color=LO, font=MONO, ha="left")
label(83, 92.4, "In-project catalog · versioned cards · name/capability search", size=7.6, color=MID, ha="left")
for i, (dept, cnt) in enumerate([("Security", "11 roles"), ("IT", "5 roles"), ("Legal", "3 roles")]):
    bx = 83 + i * 24
    box(bx, 84.0, 21, 6.2, fill=RAISED, edge=BORDER)
    label(bx + 10.5, 88.0, dept, size=8, color=HI, weight="medium")
    label(bx + 10.5, 85.6, cnt, size=6.8, color=GREEN, font=MONO)
label(153, 79.6, "catalog powers the console and /api/agents", size=6.6, color=LO, font=MONO, ha="right")

# ══════════════════════════════════════════════════════ 3. orchestrator
box(4, 69.8, 152, 9.0, fill=PANEL, edge=BORDERS)
accent(4.5, 70.5, 7.6, BLUE)
label(7.4, 75.8, "Orchestrator", size=10, color=HI, weight="medium", ha="left")
label(7.4, 72.6, "Python async coordinator · plans each sweep, fans out domains, applies verdicts, enforces budget",
      size=7.4, color=LO, font=MONO, ha="left")
for i, (pat, desc) in enumerate([("ASYNC FAN-OUT", "domain buckets"), ("ORDERED", "hunt→judge→act"), ("SCHEDULED", "sweep→recheck")]):
    bx = 96 + i * 20
    box(bx, 71.4, 18.6, 5.8, fill=RAISED, edge=BORDER)
    label(bx + 9.3, 75.0, pat, size=6.8, color=BLUE, font=MONO, weight="bold")
    label(bx + 9.3, 72.8, desc, size=6.4, color=LO, font=MONO)

arrow(39, 82.0, 39, 78.8, color=BORDERS, lw=1.3)
label(41, 80.4, "REST + SSE", size=6.6, color=LO, font=MONO, ha="left")
arrow(118, 78.8, 118, 82.0, color=BORDERS, lw=1.1, rad=0.0)
label(120, 80.4, "record()", size=6.6, color=LO, font=MONO, ha="left")

# ══════════════════════════════════════════════════════ 4. gateway bar
box(4, 63.2, 152, 4.6, fill="#16100F", edge="#4a2733", lw=1.2)
accent(4.5, 63.7, 3.6, PINK)
label(7.4, 65.5, "Application policy boundary", size=8.6, color=HI, weight="medium", ha="left")
label(36, 65.5, "connector scope guards  ·  untrusted ingress screening  ·  package egress check", size=7.2, color=MID, ha="left")
label(153, 66.4, "MODEL ARMOR / LOCAL FALLBACK", size=7.2, color=PINK, font=MONO, weight="bold", ha="right")
label(153, 64.2, "managed attempt in cloud mode  ·  deterministic detector on fallback", size=6.4, color=LO, font=MONO, ha="right")
arrow(39, 69.8, 39, 67.8, color=BORDERS, lw=1.3)

# ══════════════════════════════════════════════════════ 5. the fleet
label(4, 59.4, "11 REGISTERED ROLES  ·  SPIFFE-format labels + application-enforced scope allowlists",
      size=7.4, color=LO, font=MONO, ha="left")

hunters = [
    ("hunter/iam",    "gcp.iam.read",     BLUE),
    ("hunter/sdlc",   "github.read",      BLUE),
    ("hunter/infra",  "gcp.asset.read",   BLUE),
    ("hunter/hr",     "hris.read.redacted", BLUE),
    ("hunter/vendor", "drive.read",       PINK),
]
for i, (name, scope, col) in enumerate(hunters):
    x = 4 + i * 18.2
    node(x, 49.6, 17.0, 8.0, name, scope, color=col, tsize=7.8, ssize=6.2)
    arrow(x + 8.5, 63.2, x + 8.5, 57.6, color=BORDER, lw=0.9)

others = [
    ("control-judge", "ledger.read",   VIOLET),
    ("chaser",        "slack.write",   AMBER),
    ("sentinel",      "pubsub.publish",GREEN),
    ("assembler",     "storage.write", CYAN),
    ("redactor",      "gemma-3 helper",PINK),
]
for i, (name, scope, col) in enumerate(others):
    x = 96 + i * 12.4
    node(x, 49.6, 11.6, 8.0, name.replace("control-", ""), "", color=col, tsize=7.4)
    label(x + 6.2, 51.4, scope, size=5.8, color=LO, font=MONO)
    arrow(x + 5.8, 63.2, x + 5.8, 57.6, color=BORDER, lw=0.9)

label(4, 46.6, "separation of duties: hunters collect and never rule  ·  the judge rules and holds no collection scope",
      size=6.8, color=LO, font=MONO, ha="left")

# ══════════════════════════════════════════════════════ 6. runtime + memory
box(4, 37.4, 74, 7.4, fill=PANEL, edge=BORDER)
accent(4.5, 38.0, 6.2, BLUE)
label(7.4, 42.2, "Scheduled execution", size=8.6, color=HI, weight="medium", ha="left")
label(7.4, 39.4, "scheduled HTTP sweeps · persisted task keys · no in-progress lease recovery yet", size=6.8, color=LO, font=MONO, ha="left")

box(82, 37.4, 74, 7.4, fill=PANEL, edge=BORDER)
accent(82.5, 38.0, 6.2, GREEN)
label(85.4, 42.2, "In-project memory", size=8.6, color=HI, weight="medium", ha="left")
label(85.4, 39.4, "Firestore/in-memory beliefs · retrieved before Judge rulings", size=6.8, color=LO, font=MONO, ha="left")

for x in (40, 118):
    arrow(x, 49.6, x, 44.8, color=BORDER, lw=0.9)

# ══════════════════════════════════════════════════════ 7. infrastructure
label(4, 34.0, "GOOGLE CLOUD DEPLOYED  ·  PRIVATE  ·  SCALE TO ZERO  ·  SCHEDULER PAUSED", size=7.4, color=GREEN, font=MONO, ha="left")
infra = [
    ("Firestore",       "ledger · evidence\nhandoffs · tasks"),
    ("Pub/Sub",         "event copies\n→ atlas-events"),
    ("Cloud Scheduler", "weekly drift sweep\n→ /internal/sweep"),
    ("Model Armor",     "managed screening\n+ local fallback"),
    ("Cloud Storage",   "manifest.json\n+ SHA-256 root"),
    ("Vertex AI",       "managed Gemini\n+ optional Gemma helper"),
]
for i, (name, sub) in enumerate(infra):
    x = 4 + i * 25.4
    box(x, 22.4, 24.0, 9.4, fill=PANEL, edge=BORDER)
    accent(x + 0.5, 23.0, 8.2, GREEN)
    label(x + 12.5, 29.2, name, size=8.2, color=HI, weight="medium")
    label(x + 12.5, 25.6, sub, size=6.4, color=LO, font=MONO)
    arrow(x + 12.2, 37.4, x + 12.2, 31.8, color=BORDER, lw=0.8)

# ══════════════════════════════════════════════════════ 8. observability
box(4, 13.6, 152, 6.4, fill=PANEL, edge=BORDER)
accent(4.5, 14.2, 5.2, VIOLET)
label(7.4, 17.8, "Agent Observability", size=8.6, color=HI, weight="medium", ha="left")
label(7.4, 15.2, "OpenTelemetry → Cloud Trace  ·  operation spans + selected metadata  ·  recent spans exposed in Trace Explorer",
      size=6.9, color=LO, font=MONO, ha="left")
label(153, 16.6, "the auditor audits us", size=7.0, color=VIOLET, font=MONO, ha="right")

# ══════════════════════════════════════════════════════ 9. chain of custody
label(4, 10.0, "CHAIN OF CUSTODY", size=7.4, color=LO, font=MONO, ha="left")
hops = ["source label", "role identity", "armor status", "SHA-256", "ledger record", "manifest entry"]
for i, hop in enumerate(hops):
    x = 4 + i * 25.4
    box(x, 3.2, 21.4, 5.2, fill=RAISED, edge=BORDER)
    label(x + 10.7, 5.8, hop, size=7.2, color=MID, font=MONO)
    if i < len(hops) - 1:
        arrow(x + 21.4, 5.8, x + 25.4, 5.8, color=GREEN, lw=1.1)

ax.text(153, 0.6, "manifest integrity can be checked independently", fontsize=6.8, color=GREEN,
        family=MONO, ha="right", va="bottom")

plt.tight_layout(pad=0.3)
output = Path(__file__).resolve().parents[1] / "docs" / "architecture.png"
plt.savefig(output, facecolor=BG, dpi=170, bbox_inches="tight", pad_inches=0.28)
print(f"wrote {output}")
