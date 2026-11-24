# JAHTARIA Compliance & Prediction Evaluation Standards

Derived from `JAHTARIA_Visa_Intelligence_Engineer_Package_v01/engineering_handoff.docx`:

1. **Truthful Verification Only:** Never coach concealment, never invent ties, never imply approval guarantees.
2. **Pre-Interview Freeze:** Always freeze ranked question predictions WITH author + timestamp BEFORE the embassy interview. Never retroactively add asked questions as predictions.
3. **Policy vs. Profile Separation:** Track universal policy questions (e.g. `home_country_safety`) separately from profile-driven ranked questions so predictive recall and Precision@5 are never inflated.
4. **Known Data-Quality Traps:**
   - **Gross vs. Net JMD Salary (`C001`):** JMD 116,000 net vs ~JMD 154,875 gross is a legitimate distinction — reconcile clearly rather than assuming misrepresentation.
   - **U.S. Relatives & Fiancé(e) (`C002`, `C004`):** A question about a U.S. partner is not proof of refusal cause; never omit immediate U.S. relatives on DS-160.
   - **Legal Marital Status (`C004`):** Separated applicants without a final Decree Absolute remain legally married.
