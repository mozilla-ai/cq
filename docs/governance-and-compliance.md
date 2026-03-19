# cq: Governance and Compliance

**Status:** Draft — for review and legal input before implementation
**Date:** 2026-03-19

This document organises thinking around human-level governance of the cq knowledge commons and the legal and compliance obligations that arise from operating it. It is intended as a working document to be refined with legal counsel before any formal policies are adopted.

---

## 1. Human-Level Governance

### 1.1 Decision-Making Model

All governance decisions — including policy changes, graduation criteria, and moderation actions — require:

- **Quorum:** A minimum number of eligible reviewers must participate before a decision is valid
- **Diversity threshold:** Decisions must not be dominated by a single organisation or contributor cohort. Confirmations or votes from a single-organisation majority should be flagged for additional review
- **Transparency:** All votes, decisions, and their rationale are public records, attributable to reviewer DIDs

### 1.2 Appeal Mechanisms

Any contributor or reviewer may appeal a decision:

- Rejected KU nominations
- Flag adjudications
- Contributor or reviewer reputation actions

Appeals go to a designated appeal panel with at least one reviewer not involved in the original decision. Appeal outcomes are also public.

### 1.3 Flag Adjudication

When a KU is flagged, a formal adjudication process applies:

- Both the flagger and the contributor can present evidence
- Adjudication decisions are attributed to an adjudicator DID
- Flagging deducts a small reputation stake from the flagger, refunded if the flag is upheld
- Concentrated flagging against a single contributor triggers review of the flagger (to prevent coordinated attacks)

> **Note:** This process is partly a human governance problem and is likely to encounter friction in practice. Simulation testing of edge cases is recommended before finalising the protocol. See #100 (Simulation tests for cq) and #120 (Flag adjudication process).

### 1.4 Anti-Gaming Protections

- **Pattern detection:** Flagging concentrated on a single contributor triggers review of the flagger
- **Reviewer audit system:** StackOverflow-style review audits inject known-good/known-bad KUs into queues to catch inattentive reviewers (see #86)
- **Reviewer capacity monitoring:** Alerts when approval patterns suggest rubber-stamping
- **Double-blind graduation review:** Reviewer identities are not disclosed to each other during graduation review to prevent reputation-based bias (see #113)

---

## 2. Legal and Compliance

### 2.1 EU AI Act

**Current position:** cq's confidence scoring is statistical aggregation (confirmations, flags, confirmations from diverse sources), not model inference. This places it outside the high-risk AI system classification under the EU AI Act.

**Trigger for reassessment:** If retrieval moves from keyword/tag matching to semantic/vector search with learned embeddings, the classification argument should be reviewed with legal counsel.

**Audit trail:** cq's `provenance.graduation_history` schema provides per-graduation records of reviewer DID and timestamp, supporting Articles 11, 12, and 13 obligations. See #86 (Audit log).

### 2.2 GDPR

**Data controller:** Whoever operates the commons tier (team or global) is the data controller for KU content and provenance records stored in that tier. This must be clearly stated in the contributor agreement.

**Data subject rights:**

| Right | Implementation path |
|---|---|
| Right of access | Query endpoint for KUs contributed by a given DID |
| Right to erasure | Flagging mechanism provides the removal path; flagged KUs can be withdrawn and re-reviewed |
| Right to portability | Export endpoint for KU content contributed by a DID |
| Right to object | Contributor agreement defines scope of processing; objections go to the appeal process |

**Selective erasure:** KERI's non-intertwined trust bases support removing one contributor's data without affecting others' trust chains.

**Retention periods:** TBD — requires legal input. Suggested starting point: active KU data retained for the lifetime of the commons; provenance records retained for regulatory audit purposes (minimum 5 years, following EU AI Act record-keeping norms).

> **Open question for legal counsel:** Does the provenance record (which includes reviewer DIDs) constitute personal data? If so, what is the lawful basis for processing it?

### 2.3 Contributor Agreement

The contributor agreement must address:

- **Limitation of liability:** The commons does not guarantee accuracy, safety, or fitness for purpose. Contributors are responsible for the content they submit
- **KU action field framing:** The `action` field in KU content should be framed as guidance ("consider", "verify") not instruction ("always", "must"). Contributors should be informed of this expectation
- **Data controller designation:** Contributors grant the commons operator a licence to store, process, and share the KU content under the chosen content licence
- **Content licence:** Decision required. Options:
  - CC-BY-SA (share-alike, attribution required)
  - CC0 (public domain dedication)
  - Apache 2.0 for data (permissive, compatible with open source tooling)

> **Action item:** Select content licence before the global commons is opened for contributions.

### 2.4 AI Liability

The KU `action` field creates a potential liability surface if agents act on KU guidance and cause harm. Mitigations:

- Framing in the skill and contributor agreement: KU content is advisory, not authoritative
- Monitoring for precedent-setting cases in AI liability law (EU, US, UK) that could affect the commons model
- Limitation of liability clause in contributor agreement

### 2.5 Smart Contract Jurisdiction (if staking is implemented)

If #131 (Staking mechanism) is implemented using on-chain smart contracts:

- Jurisdiction of the contract must be determined
- Slashing logic is subject to consumer protection law in some jurisdictions
- Legal review of the contract before deployment is required

---

## 3. Open Questions for Legal Counsel

1. **Global commons data controller:** Who is the data controller when KUs are stored in the global public commons? Is it Mozilla AI, or is it a shared controller arrangement with contributing organisations?

2. **Cross-border data transfer:** If the global commons stores KUs contributed by EU-based agents, does the data residency of the global store matter? Are standard contractual clauses needed?

3. **Provenance records as personal data:** Does a reviewer DID in `provenance.graduation_history` constitute personal data under GDPR? If so, what is the retention policy and lawful basis?

4. **Smart contract jurisdiction:** If staking is on-chain (Cardano), in which jurisdiction does the contract operate? Is slashing enforceable?

5. **AI Act future-proofing:** How should cq's architecture evolve to remain compliant if the EU AI Act's scope is extended to cover systems like cq in future revisions?

6. **Liability exposure:** What is Mozilla AI's liability exposure if a KU contains inaccurate information that causes an agent to make a harmful decision?

---

## 4. Related GitHub Issues

| Area | Issue |
|---|---|
| Audit log and EU AI Act compliance | #86 |
| GDPR data subject rights and right to erasure | #133 |
| Zero knowledge proof for GDPR compliance | #140 |
| Query log retention and privacy | #134 |
| Session context privacy enforcement | #132 |
| Submission timing anonymisation | #135 |
| Flag adjudication process | #120 |
| Double blind review | #113 |
| Staking mechanism | #131 |
| DID/KERI agent identity | #142 |
| Global store provenance enforcement | #126 |
| Simulation tests | #100 |
