"""SOC 2 Trust Services Criteria — the 64 controls ATLAS works on.

Criterion text is paraphrased for the demo; the structure (CC1–CC9, A1, C1,
PI1, P1) mirrors TSC 2017 so the ledger looks right to anyone who has sat
through a real audit.
"""
from __future__ import annotations

from app.core.models import Domain

# (id, name, domain, criterion text, evidence_required, freshness_days)
CONTROLS: list[tuple[str, str, Domain, str, int, int]] = [
    # ---- CC1 Control Environment
    ("CC1.1", "Integrity and ethical values", Domain.HR, "The entity demonstrates a commitment to integrity and ethical values through a documented code of conduct acknowledged by all personnel.", 2, 365),
    ("CC1.2", "Board independence and oversight", Domain.HR, "The board of directors demonstrates independence from management and exercises oversight of internal control.", 2, 365),
    ("CC1.3", "Organisational structure and authority", Domain.HR, "Management establishes structures, reporting lines, and appropriate authorities and responsibilities.", 2, 365),
    ("CC1.4", "Competence and security training", Domain.HR, "The entity demonstrates a commitment to attract, develop, and retain competent individuals, including annual security awareness training.", 2, 365),
    ("CC1.5", "Accountability for internal control", Domain.HR, "The entity holds individuals accountable for their internal control responsibilities.", 2, 365),
    # ---- CC2 Communication and Information
    ("CC2.1", "Quality information for internal control", Domain.INFRA, "The entity obtains or generates relevant, quality information to support the functioning of internal control.", 3, 180),
    ("CC2.2", "Internal communication of responsibilities", Domain.HR, "The entity internally communicates information, including objectives and responsibilities for internal control.", 2, 365),
    ("CC2.3", "External communication", Domain.VENDOR, "The entity communicates with external parties regarding matters affecting the functioning of internal control.", 2, 365),
    # ---- CC3 Risk Assessment
    ("CC3.1", "Objectives specified for risk assessment", Domain.INFRA, "The entity specifies objectives with sufficient clarity to enable identification and assessment of risks.", 2, 365),
    ("CC3.2", "Risk identification and analysis", Domain.INFRA, "The entity identifies risks to the achievement of its objectives and analyses them as a basis for determining how they should be managed.", 3, 180),
    ("CC3.3", "Fraud risk consideration", Domain.HR, "The entity considers the potential for fraud in assessing risks.", 2, 365),
    ("CC3.4", "Change risk assessment", Domain.SDLC, "The entity identifies and assesses changes that could significantly impact the system of internal control.", 3, 180),
    # ---- CC4 Monitoring Activities
    ("CC4.1", "Ongoing and separate evaluations", Domain.INFRA, "The entity selects, develops, and performs ongoing and separate evaluations to ascertain whether components of internal control are present and functioning.", 3, 180),
    ("CC4.2", "Deficiency communication", Domain.INFRA, "The entity evaluates and communicates internal control deficiencies in a timely manner to those responsible for corrective action.", 2, 180),
    # ---- CC5 Control Activities
    ("CC5.1", "Control activity selection", Domain.INFRA, "The entity selects and develops control activities that contribute to the mitigation of risks to acceptable levels.", 3, 180),
    ("CC5.2", "Technology general controls", Domain.SDLC, "The entity selects and develops general control activities over technology to support the achievement of objectives.", 3, 180),
    ("CC5.3", "Policy deployment", Domain.HR, "The entity deploys control activities through policies that establish what is expected and procedures that put policies into action.", 3, 365),
    # ---- CC6 Logical and Physical Access
    ("CC6.1", "Logical access — least privilege and deprovisioning", Domain.IAM, "The entity implements logical access security software, infrastructure, and architectures over protected information assets. Access is provisioned on least privilege, reviewed quarterly, and deprovisioned within 24 hours of role change or termination.", 3, 90),
    ("CC6.2", "Authentication and MFA enforcement", Domain.IAM, "Prior to issuing system credentials, the entity registers and authorises new internal and external users, and enforces multi-factor authentication.", 2, 90),
    ("CC6.3", "Role-based access authorisation", Domain.IAM, "The entity authorises, modifies, or removes access to data, software, and functions based on roles, responsibilities, and least privilege.", 3, 90),
    ("CC6.4", "Physical access restriction", Domain.INFRA, "The entity restricts physical access to facilities and protected information assets.", 2, 365),
    ("CC6.5", "Secure asset disposal", Domain.INFRA, "The entity discontinues logical and physical protections over physical assets only after the ability to read or recover data has been diminished.", 2, 365),
    ("CC6.6", "Boundary protection and segmentation", Domain.INFRA, "The entity implements logical access security measures to protect against threats from sources outside its system boundaries.", 3, 90),
    ("CC6.7", "Data transmission and movement", Domain.INFRA, "The entity restricts the transmission, movement, and removal of information to authorised users and protects it during transmission.", 3, 90),
    ("CC6.8", "Malicious software prevention", Domain.INFRA, "The entity implements controls to prevent or detect and act upon the introduction of unauthorised or malicious software.", 2, 90),
    # ---- CC7 System Operations
    ("CC7.1", "Vulnerability management and patch cadence", Domain.INFRA, "The entity uses detection and monitoring procedures to identify changes to configurations that introduce new vulnerabilities, and remediates on a documented cadence.", 3, 90),
    ("CC7.2", "Monitoring and alert coverage", Domain.INFRA, "The entity monitors system components for anomalies indicative of malicious acts, natural disasters, and errors, with tested alerting for every production service.", 3, 90),
    ("CC7.3", "Security incident evaluation", Domain.INFRA, "The entity evaluates security events to determine whether they could or have resulted in a failure to meet objectives.", 2, 180),
    ("CC7.4", "Incident response", Domain.INFRA, "The entity responds to identified security incidents by executing a defined incident response programme.", 2, 180),
    ("CC7.5", "Incident recovery", Domain.INFRA, "The entity identifies, develops, and implements activities to recover from identified security incidents.", 2, 180),
    # ---- CC8 Change Management
    ("CC8.1", "Change management and PR review enforcement", Domain.SDLC, "The entity authorises, designs, develops, configures, documents, tests, approves, and implements changes to infrastructure, data, software, and procedures. Every production change carries an approving review.", 3, 90),
    # ---- CC9 Risk Mitigation
    ("CC9.1", "Business disruption risk mitigation", Domain.INFRA, "The entity identifies, selects, and develops risk mitigation activities for risks arising from potential business disruptions.", 2, 365),
    ("CC9.2", "Vendor and business partner risk", Domain.VENDOR, "The entity assesses and manages risks associated with vendors and business partners, including current data processing agreements and reviewed SOC 2 reports.", 3, 365),
    # ---- A1 Availability
    ("A1.1", "Capacity management", Domain.INFRA, "The entity maintains, monitors, and evaluates current processing capacity and use of system components.", 2, 90),
    ("A1.2", "Backup and environmental protection", Domain.INFRA, "The entity authorises, designs, develops, implements, operates, and maintains backup processes and recovery infrastructure.", 3, 90),
    ("A1.3", "Recovery testing", Domain.INFRA, "The entity tests recovery plan procedures supporting system recovery.", 2, 365),
    # ---- C1 Confidentiality
    ("C1.1", "Confidential information identification", Domain.INFRA, "The entity identifies and maintains confidential information to meet its confidentiality objectives.", 2, 180),
    ("C1.2", "Confidential information disposal", Domain.INFRA, "The entity disposes of confidential information to meet its confidentiality objectives.", 2, 365),
    # ---- PI1 Processing Integrity
    ("PI1.1", "Processing accuracy and completeness", Domain.SDLC, "The entity obtains or generates, uses, and communicates relevant, quality information regarding processing objectives.", 2, 180),
    ("PI1.2", "Input validation", Domain.SDLC, "The entity implements policies and procedures over system inputs to result in products and services meeting specifications.", 2, 180),
    # ---- P1 Privacy
    ("P1.1", "Privacy notice", Domain.VENDOR, "The entity provides notice to data subjects about its privacy practices.", 2, 365),
    ("P1.2", "Choice and consent", Domain.VENDOR, "The entity communicates choices available regarding the collection, use, retention, disclosure, and disposal of personal information.", 2, 365),
    ("P1.3", "Collection limitation", Domain.HR, "The entity collects personal information consistent with its objectives related to privacy.", 2, 365),
    ("P1.4", "Use and retention", Domain.INFRA, "The entity limits the use and retention of personal information to its stated purposes.", 2, 365),
    ("P1.5", "Access by data subjects", Domain.IAM, "The entity grants identified data subjects the ability to access their personal information.", 2, 365),
    ("P1.6", "Disclosure to third parties", Domain.VENDOR, "The entity discloses personal information to third parties only with consent and consistent with its objectives.", 2, 365),
    ("P1.7", "Quality of personal information", Domain.INFRA, "The entity maintains accurate, up-to-date, complete, and relevant personal information.", 2, 365),
    ("P1.8", "Monitoring and enforcement of privacy", Domain.VENDOR, "The entity monitors compliance with its privacy objectives and addresses privacy-related inquiries and disputes.", 2, 365),
]

# Pad to a full 64-control ledger with per-domain operational sub-controls.
_EXTRA_TEMPLATES = [
    ("CC6", Domain.IAM, "Quarterly access recertification for {n}", 2, 90),
    ("CC7", Domain.INFRA, "Endpoint hardening baseline for {n}", 2, 90),
    ("CC8", Domain.SDLC, "Release approval evidence for {n}", 2, 90),
    ("CC3", Domain.VENDOR, "Sub-processor review for {n}", 2, 180),
    ("CC2", Domain.HR, "Policy attestation cycle for {n}", 2, 365),
]
_TARGETS = ["production", "corporate IT", "the data platform", "customer-facing services"]

_i = 0
while len(CONTROLS) < 64:
    group, domain, template, req, fresh = _EXTRA_TEMPLATES[_i % len(_EXTRA_TEMPLATES)]
    target = _TARGETS[(_i // len(_EXTRA_TEMPLATES)) % len(_TARGETS)]
    seq = 90 + _i
    name = template.format(n=target)
    CONTROLS.append(
        (
            f"{group}.{seq}",
            name,
            domain,
            f"The entity performs and evidences {name.lower()} on the documented cadence.",
            req,
            fresh,
        )
    )
    _i += 1

OWNERS = {
    Domain.IAM: "dev",
    Domain.SDLC: "dev",
    Domain.INFRA: "dev",
    Domain.HR: "priya",
    Domain.VENDOR: "priya",
}

# Beliefs the fleet carries into this audit from last year's run.
PRIOR_MEMORIES: list[tuple[str, str, float]] = [
    ("CC6.1", "Priya rejects screenshot evidence for CC6.1 — she requires exported JSON from the IAM API.", 0.94),
    ("", "Auditor (Alex, Schellman) requires a SHA-256 manifest for all artifacts over 1MB.", 0.99),
    ("", "Dev responds to Slack nudges within ~4h on weekdays, never on weekends. Do not escalate before 72h.", 0.88),
    ("CC9.2", "Vendor Northwind Analytics lets its DPA lapse every March — request renewal in February.", 0.91),
    ("CC7.2", "CC7.2 alert-coverage evidence must include the PagerDuty integration test, not just the config export.", 0.86),
    ("CC6.1", "Break-glass access is permitted for CC6.1 if logged and reviewed within 24h. Precedent set in the 2025 audit.", 1.0),
]
