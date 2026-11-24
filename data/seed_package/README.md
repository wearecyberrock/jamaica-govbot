# JAHTARIA VISA INTELLIGENCE — ENGINEERING HANDOFF (v0.1)

This is a **source-indexed, pseudonymized starter corpus**, not a complete export of every previous conversation or an approved model-training set.

## Contents
- `cases_pseudonymized.jsonl` / `.csv`: case-level attributes, predicted themes, observed question themes, outcomes, evidence flags.
- `interview_events.jsonl`: one row per user-reported interview question theme; order is NOT necessarily the actual interview order.
- `question_taxonomy.csv`: stable theme vocabulary and sample paraphrases.
- `source_manifest.csv` / `.json`: 83 local files indexed with hashes, type, extraction status and provenance. Original files are **not** embedded.
- `engineering_handoff.docx`: methodology, schema and rollout plan.

## Critical limits
- The original 83 source files contain sensitive personal and immigration information and have not been included in this package. Their presence in the manifest does not authorize sharing them with a third party.
- Some sources are assessments written after a screening rather than verbatim transcripts.
- Reported embassy questions are recollections, not official transcripts. The event sequence numbers are export order, not established embassy order.
- Some case details are known only from the user's conversation, not directly verified in uploaded documents.
- Several different people share a first name (e.g. Shanice). Do not merge based on first name.
- No client consent to AI training has been verified. Require documented, purpose-specific authorization and appropriate retention/access controls before ingesting identifiable material.
- Do not train a model to produce a numerical approval probability from this small, nonrandom, selection-biased sample.

## Recommended data model
`clients` (random case ID only), `source_documents` (hash, version, capture time, uploader, sensitivity), `profile_facts` (value, as-of date, evidence, confidence), `ds160_versions` (submitted/draft distinction), `screening_events`, `predictions` (timestamped before embassy, rank, question, theme), `mock_interviews` (asked, answer, discrepancy, resolution), `embassy_interviews` (actual question, exact-vs-paraphrase, answer), `outcomes` (visa class, statute if evidenced), `consents`, `audit_log`.

## Evaluation
Freeze predictions before interview; track exact-match and thematic recall separately, precision@5, calibration of ranked questions, questions missed, and data-quality coverage. Evaluate by time split and client-level separation. Maintain separate mandatory policy-question checklist; do not inflate predictive metrics by counting universal questions as profile predictions.

## Compliance
System must assist truthful application verification and accurate, spontaneous answers. Never coach concealment, invent ties, infer officer motives as fact, or imply visa approval guarantees. Flag contradictions (e.g. gross vs net income, U.S. relatives, marital legal status, travel chronology) for human review.
