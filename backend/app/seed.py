"""Idempotent database & Obsidian Vault seeder using JAHTARIA_Visa_Intelligence_Engineer_Package_v01 and official PDFs."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from docx import Document as DocxDocument
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import (
    BLUEPRINTS_DIR,
    OBSIDIAN_VAULT_DIR,
    OFFICIAL_PDFS_DIR,
    SEED_CEO_EMAIL,
    SEED_CEO_PASSWORD,
    SEED_CLIENT_EMAIL,
    SEED_CLIENT_PASSWORD,
    SEED_PACKAGE_DIR,
    SEED_STAFF_EMAIL,
    SEED_STAFF_PASSWORD,
    encrypt_value,
)
from app.models import (
    BrandingConfig,
    ClientCase,
    EmailAutomationRule,
    GeneratedAsset,
    GovSource,
    InterviewEvent,
    OfficialDocument,
    PipelineJournal,
    ProfileFact,
    QuestionTaxonomy,
    SourceManifestItem,
    User,
)
from app.services.doc_generator import (
    generate_ds160_worksheet_pdf,
    generate_kingston_checklist_pdf,
    generate_visual_roadmap_png,
    inspect_blueprint_file,
)
from app.services.obsidian import sync_client_to_obsidian, write_vault_note
from app.services.risk_engine import evaluate_client_standing, generate_ranked_predictions

OFFICIAL_GOV_SOURCES = [
    {
        "source_key": "us_embassy_kingston_visas",
        "name": "U.S. Embassy in Jamaica — Visas & Nonimmigrant Hub",
        "agency": "U.S. Embassy Kingston",
        "category": "us_embassy",
        "url": "https://jm.usembassy.gov/visas/",
        "verified_summary": (
            "Primary consular guidance for U.S. Embassy Kingston (142 Old Hope Road, Kingston; Tel: 876-702-6000). "
            "Covers DS-160 submission, AIS appointment scheduling (ais.usvisa-info.com/en-jm/niv), minor accompaniment under 18, "
            "Sept 6 2025 resident-country NIV rule, and Form DS-5535 submission to KingstonNIV@state.gov ONLY when requested."
        ),
        "key_rules": [
            "Embassy address: 142 Old Hope Road, Kingston (Mon-Fri 7:30am-4:00pm).",
            "Minors under 18 must be accompanied by a parent or legal guardian.",
            "As of Sept 6, 2025, NIV applicants should apply in their country of residence or nationality.",
            "Form DS-5535 only if requested: email PDF to KingstonNIV@state.gov with subject 'V11 - DS-5535 - [SURNAME, GIVEN NAME]'.",
        ],
    },
    {
        "source_key": "us_embassy_kingston_barcode_rule",
        "name": "U.S. Embassy Kingston — Mandatory DS-160 Barcode Match Policy",
        "agency": "U.S. Embassy Kingston",
        "category": "us_embassy",
        "url": "https://jm.usembassy.gov/correct-ds-160-barcodes-are-required-for-all-appointments/",
        "verified_summary": (
            "Effective April 1, 2025: ALL visa applicants at U.S. Embassy Kingston must bring a printed DS-160 confirmation page "
            "whose AA barcode number EXACTLY matches the barcode used to book the interview on ais.usvisa-info.com/en-jm/niv. "
            "Applicants with mismatched barcodes are refused entry and must rebook."
        ),
        "key_rules": [
            "Effective April 1, 2025 — strictly enforced at Old Hope Road check-in.",
            "DS-160 confirmation number begins with 'AA' and must match AIS portal record.",
            "If a new DS-160 is submitted, update AIS profile at least 48 hours prior to interview.",
        ],
    },
    {
        "source_key": "dos_kingston_post_supplement",
        "name": "U.S. Dept. of State — Kingston (KNG) Post Pre-Interview Supplement",
        "agency": "U.S. Department of State",
        "category": "us_dos",
        "url": "https://travel.state.gov/content/travel/en/us-visas/Supplements/Supplements_by_Post/KNG-Kingston.html",
        "verified_summary": (
            "Official Kingston Post checklist: unexpired passport valid 6+ months beyond intended U.S. entry, 2x2 inch (5x5 cm) white-background photos, "
            "Jamaican RGD civil documents copied at 92% scale so top & bottom serial numbers are preserved, prohibited items (no cellphones/storage at Old Hope Rd), "
            "and rules on who may accompany applicants."
        ),
        "key_rules": [
            "Passport must be valid at least 6 months past intended entry.",
            "CRITICAL: Reduce Jamaican RGD birth/marriage certificate photocopies to 92% so serial numbers are not cut off.",
            "Cellphones and electronics are prohibited inside Consular Section; no storage facilities exist.",
            "Attorneys cannot enter interview waiting room; parents/guardians accompany minors.",
        ],
    },
    {
        "source_key": "dos_ds160_guide",
        "name": "Form DS-160 Online Nonimmigrant Visa Application",
        "agency": "U.S. Department of State",
        "category": "us_dos",
        "url": "https://travel.state.gov/content/travel/en/us-visas/visa-information-resources/forms/ds-160-online-nonimmigrant-visa-application.html",
        "verified_summary": (
            "Form DS-160 is submitted electronically via CEAC (ceac.state.gov) for all nonimmigrant visas (B1/B2, F-1, H-2B, J-1). "
            "Once submitted, DS-160 cannot be edited — corrections require a new DS-160 and updating the AIS appointment barcode. "
            "Requires accurate employment, gross monthly income, U.S. contacts, immediate U.S. relatives, and prior refusal disclosure."
        ),
        "key_rules": [
            "Submitted electronically at ceac.state.gov; print barcode confirmation page.",
            "Cannot be edited after submission — verify Gross JMD salary, marital status, and U.S. relatives BEFORE signing.",
            "Inconsistencies with supporting documents cause INA 221(g) delays or credibility refusals.",
        ],
    },
    {
        "source_key": "dos_visa_fees",
        "name": "U.S. Visa MRV Application Fees & Reciprocity Schedule",
        "agency": "U.S. Department of State",
        "category": "fees",
        "url": "https://travel.state.gov/content/travel/en/us-visas/visa-information-resources/fees/fees-visa-services.html",
        "verified_summary": (
            "Official Machine Readable Visa (MRV) processing fees: $185 USD for B-1/B-2 Visitor, F-1 Student, and J-1 Exchange visas; "
            "$205 USD for petition-based H-2B/L/O/P/Q/R work visas; $265 USD for K fiancé(e) visas; $315 USD for E treaty visas. "
            "F-1/J-1 applicants also pay the separate SEVIS I-901 fee ($350 for F-1)."
        ),
        "key_rules": [
            "B-1/B-2 Visitor, F-1 Student, J-1 Exchange MRV fee: $185 USD (non-refundable).",
            "H-2B / Petition-based worker MRV fee: $205 USD.",
            "K Fiancé(e) visa fee: $265 USD; E Treaty visa fee: $315 USD.",
            "F-1 Student SEVIS I-901 fee: $350 USD paid separately before interview.",
        ],
    },
    {
        "source_key": "dos_visitor_visa_214b",
        "name": "Visitor Visa (B-1/B-2) Eligibility & INA Section 214(b) Ties",
        "agency": "U.S. Department of State",
        "category": "us_dos",
        "url": "https://travel.state.gov/content/travel/en/us-visas/tourism-visit/visitor.html",
        "verified_summary": (
            "Outlines B-1 business and B-2 tourism eligibility, required vs optional supporting documents, and INA Section 214(b) presumption of immigrant intent. "
            "Applicants demonstrate strong social, family, and economic ties to Jamaica and truthful temporary travel intent."
        ),
        "key_rules": [
            "INA 214(b) requires demonstrating binding social/economic ties outside the U.S.",
            "Documents are supporting aids; consular officers rely primarily on DS-160 accuracy and concise truthful interview answers.",
            "Never purchase non-refundable tickets before visa issuance.",
        ],
    },
    {
        "source_key": "ais_jamaica_niv",
        "name": "Official U.S. Visa Appointment & Courier Portal (Jamaica)",
        "agency": "AIS / U.S. Visa Info Jamaica",
        "category": "us_embassy",
        "url": "https://ais.usvisa-info.com/en-jm/niv",
        "verified_summary": (
            "Official portal to pay MRV fees, schedule/reschedule Kingston Embassy nonimmigrant visa appointments, "
            "sync DS-160 AA confirmation barcodes, and register DHL courier return location for passport delivery."
        ),
        "key_rules": [
            "Mandatory free courier registration for passport return after interview.",
            "Call Center (Jamaica): 876-656-8535 / 876-630-2040 (Mon-Fri 9am-5pm).",
            "Emergency interview requests go through AIS or kingstonnivemergency@state.gov.",
        ],
    },
    {
        "source_key": "ceac_portal",
        "name": "Consular Electronic Application Center (CEAC)",
        "agency": "U.S. Department of State",
        "category": "us_dos",
        "url": "https://ceac.state.gov/",
        "verified_summary": (
            "Official U.S. Department of State portal for filling Form DS-160 (Nonimmigrant), Form DS-260 (Immigrant), "
            "uploading digital 2x2 photo, and checking live visa application status (Issued, Refused, Administrative Processing)."
        ),
        "key_rules": [
            "Save Application ID (AA...) and security question immediately upon starting DS-160.",
            "Check live case status at ceac.state.gov/CEACStatTracker.",
        ],
    },
    {
        "source_key": "pica_passport_apply",
        "name": "PICA Jamaica — Applying for a Jamaican Passport (Adult & Minor)",
        "agency": "PICA Jamaica",
        "category": "jamaica_passport",
        "url": "https://www.pica.gov.jm/passport/apply",
        "verified_summary": (
            "Official Passport, Immigration and Citizenship Agency (PICA) requirements for first-time adult & minor Jamaican passports. "
            "Head Office: 25C Constant Spring Road, Kingston (Tel: 876-754-7422). Requires certified application form, RGD birth certificate, two identical compliant photos, and valid ID."
        ),
        "key_rules": [
            "Head Office: 25C Constant Spring Road, Kingston (Tel: 876-754-7422 / 754-PICA).",
            "Minors under 18 require Sections C & E signed by parent/legal guardian.",
            "First-time applicants require certified photos & original RGD birth certificate.",
        ],
    },
    {
        "source_key": "pica_passport_renew",
        "name": "PICA Jamaica — Renewing a Jamaican Adult Passport (Simplified & Online)",
        "agency": "PICA Jamaica",
        "category": "jamaica_passport",
        "url": "https://www.pica.gov.jm/passport/renew",
        "verified_summary": (
            "Adult Jamaican citizens (18+ at previous 10-year passport issue, no name or marital status change, undamaged passport) "
            "may renew online via passport.pica-online.com or submit the Simplified Adult Renewal Form 1 with current passport and 2 identical photos."
        ),
        "key_rules": [
            "Online Adult Renewal Portal: https://passport.pica-online.com/",
            "Simplified Form 1 eligible only if undamaged, 10-yr adult passport, no name/marital change.",
            "Renew BEFORE applying for U.S. visa if less than 6 months validity remain.",
        ],
    },
    {
        "source_key": "pica_passport_fees",
        "name": "PICA Jamaica — Official Passport Processing Fees & Turnaround",
        "agency": "PICA Jamaica",
        "category": "fees",
        "url": "https://www.pica.gov.jm/passport/fees",
        "verified_summary": (
            "Official PICA fee schedule for regular, next-day, and same-day expedited Jamaican passport processing in Kingston & Montego Bay, "
            "plus overseas mission USD/GBP fee tables and lost/damaged passport surcharges."
        ),
        "key_rules": [
            "Local payment accepted in Jamaican Dollars (JMD); check latest expedited availability at Constant Spring Rd.",
            "Damaged or lost passports require PICA Customer Service review and police report (if lost/stolen).",
        ],
    },
    {
        "source_key": "rgd_nira_certificates",
        "name": "RGD / NIRA Jamaica — Birth, Marriage & Civil Certificates",
        "agency": "RGD / NIRA Jamaica",
        "category": "jamaica_civil",
        "url": "https://nira.gov.jm/birth-certificate/",
        "verified_summary": (
            "Official Registrar General's Department (RGD / NIRA, Twickenham Park, St. Catherine; apps2.rgd.gov.jm) portal for obtaining "
            "computer-generated certified copies of Jamaican birth, marriage, and deed poll certificates required for U.S. visa verification."
        ),
        "key_rules": [
            "Online ordering portal: https://apps2.rgd.gov.jm/ (Tel: 876-749-0550).",
            "Always request the computer-generated security paper certificate with serial numbers intact.",
            "Photocopy at 92% scale for U.S. Embassy Kingston submission.",
        ],
    },
]

OFFICIAL_PDF_CATALOG = [
    {
        "doc_key": "pica_passport_full_form",
        "filename": "PICA_Jamaica_Passport_Application_Form.pdf",
        "title": "PICA Jamaican Passport Application Form (Adult & Minor)",
        "agency": "PICA Jamaica",
        "category": "official_pdf",
        "source_url": "https://www.pica.gov.jm/sites/default/files/Forms/Jamaica-Passport-Application-Compressed.pdf",
        "description": "Official PICA Jamaica application form for first-time adult/minor passports, lost/damaged replacements, and name/marital changes.",
    },
    {
        "doc_key": "pica_adult_renewal_simplified",
        "filename": "PICA_Adult_Passport_Renewal_Simplified.pdf",
        "title": "PICA Simplified Adult Passport Renewal Form (Form 1)",
        "agency": "PICA Jamaica",
        "category": "official_pdf",
        "source_url": "https://www.pica.gov.jm/sites/default/files/Forms/Adult%20Renewal%20Form%20%28Simplified%29.pdf",
        "description": "Official PICA simplified 2-page renewal form for eligible adult 10-year Jamaican passports expiring within 1 year.",
    },
    {
        "doc_key": "pica_adult_renewal_instructions",
        "filename": "PICA_Adult_Renewal_Instruction_Sheet.pdf",
        "title": "PICA Adult Passport Renewal Instruction Sheet",
        "agency": "PICA Jamaica",
        "category": "instruction_sheet",
        "source_url": "https://www.pica.gov.jm/sites/default/files/Forms/Instruction-Sheet-Adult-Renewal-form-Final.pdf",
        "description": "Eligibility checklist, photo specifications, and submission instructions for PICA Simplified Adult Renewal.",
    },
    {
        "doc_key": "pica_declaration_form",
        "filename": "PICA_Declaration_Form.pdf",
        "title": "PICA Statutory Declaration Form",
        "agency": "PICA Jamaica",
        "category": "official_pdf",
        "source_url": "https://www.pica.gov.jm/sites/default/files/Forms/Declaration-Form.pdf",
        "description": "Official PICA declaration form used when supporting civil/identity particulars require formal declaration.",
    },
    {
        "doc_key": "pica_citizenship_descent",
        "filename": "PICA_Citizenship_by_Descent_Form.pdf",
        "title": "PICA Citizenship by Descent Application Form",
        "agency": "PICA Jamaica",
        "category": "official_pdf",
        "source_url": "https://www.pica.gov.jm/sites/default/files/Forms/Citizenship%20by%20Descent%20Application%20Form.pdf",
        "description": "Official PICA citizenship by descent application & local/overseas fee & document requirements.",
    },
    {
        "doc_key": "us_dos_ds5535",
        "filename": "US_DOS_Form_DS5535_Supplemental_Questions.pdf",
        "title": "U.S. Dept. of State Form DS-5535 (Supplemental Questions — 221(g))",
        "agency": "U.S. Department of State",
        "category": "official_pdf",
        "source_url": "https://jm.usembassy.gov/visas/",
        "description": "Official 3-page Form DS-5535 for Administrative Processing (15-year travel/address/employment & 5-year social media history). Submit ONLY if requested by KingstonNIV@state.gov.",
    },
    {
        "doc_key": "us_dos_ds157",
        "filename": "US_DOS_Form_DS157_Supplemental_NIV.pdf",
        "title": "U.S. Dept. of State Form DS-157 (Supplemental Nonimmigrant Visa)",
        "agency": "U.S. Department of State",
        "category": "official_pdf",
        "source_url": "https://eforms.state.gov/Forms/ds157.PDF",
        "description": "Official U.S. Department of State supplemental nonimmigrant visa reference form.",
    },
    {
        "doc_key": "us_dos_ds156e",
        "filename": "US_DOS_Form_DS156E_Treaty_Trader.pdf",
        "title": "U.S. Dept. of State Form DS-156E (Treaty Trader / Investor)",
        "agency": "U.S. Department of State",
        "category": "official_pdf",
        "source_url": "https://eforms.state.gov/Forms/ds156_e.PDF",
        "description": "Official U.S. Department of State Form DS-156E used alongside DS-160 for E-1/E-2 business/investor visas.",
    },
    {
        "doc_key": "rgd_birth_cert_birreq",
        "filename": "RGD_Jamaica_Birth_Certificate_Application_BIRREQ.pdf",
        "title": "RGD Jamaica Birth Certificate Certified Copy Application (BIRREQ)",
        "agency": "RGD Jamaica",
        "category": "official_pdf",
        "source_url": "https://nira.gov.jm/birth-certificate/",
        "description": "Official Registrar General's Department application for certified computer-generated Jamaican Birth Certificate.",
    },
    {
        "doc_key": "embassy_ja_passport_guidelines",
        "filename": "Embassy_of_Jamaica_Passport_Renewal_Guidelines.pdf",
        "title": "Embassy of Jamaica — Passport Renewal Guidelines (Adults & Minors)",
        "agency": "Embassy of Jamaica / MFAFT",
        "category": "instruction_sheet",
        "source_url": "https://www.embassyofjamaica.org/ja_citizens/passport_renewal_application_guidelines.pdf",
        "description": "Complete adult and minor Jamaican passport renewal checklist, photo guidelines, and turnaround summary.",
    },
    {
        "doc_key": "embassy_ja_birth_cert_guide",
        "filename": "Embassy_of_Jamaica_Birth_Certificate_Guide.pdf",
        "title": "Embassy of Jamaica — Applying for a Jamaican Birth Certificate",
        "agency": "Embassy of Jamaica / MFAFT",
        "category": "instruction_sheet",
        "source_url": "https://www.embassyofjamaica.org/ja_citizens/birth_certification_application.pdf",
        "description": "Official step-by-step instructions for ordering Jamaican RGD birth certificates.",
    },
]


def _ensure_default_docx_blueprint() -> Path:
    bp_path = BLUEPRINTS_DIR / "Jahtaria_Employment_Trip_Support_Template.docx"
    if not bp_path.exists():
        doc = DocxDocument()
        doc.add_heading("Jahtaria Travel Services — Client Visa Verification Blueprint", level=1)
        doc.add_paragraph("Case ID: {{case_id}}   |   Visa Class: {{visa_class}}   |   Date: {{generated_date}}")
        doc.add_paragraph("Applicant Full Name: {{full_name}} ({{nationality}}, {{parish}})")
        doc.add_paragraph("Passport Number: {{passport_number}}   |   Expiry: {{passport_expiry}}")
        doc.add_paragraph("DS-160 Barcode: {{ds160_confirmation_id}}   |   AIS Barcode: {{ais_appointment_barcode}}")
        doc.add_paragraph("Occupation & Employer: {{occupation}} at {{employer_name}}")
        doc.add_paragraph("Verified Monthly Salary: Gross {{monthly_gross_jmd}} / Net {{monthly_net_jmd}}")
        doc.add_paragraph("Travel Plan: {{purpose_of_trip}} in {{us_destination}} ({{intended_travel_date}} to {{intended_return_date}})")
        doc.add_paragraph("U.S. Contact / Host: {{us_host_contact}}   |   U.S. Relatives: {{us_relatives_details}}")
        doc.add_paragraph("Good Standing Readiness Score: {{standing_score}}")
        doc.save(str(bp_path))
    return bp_path


def _seed_obsidian_vault() -> None:
    if (OBSIDIAN_VAULT_DIR / "Index.md").exists():
        return

    write_vault_note(
        "Index.md",
        """# Jahtaria Travel Services — Visa Intelligence Vault

Welcome to the local **Obsidian-compatible Knowledge & Case Vault** (`data/obsidian-vault/`).
Open this folder directly in the Obsidian desktop app OR browse & edit notes right inside the Staff & CEO dashboards.

## Core Official Knowledge Notes
- [[Gov-Rules/US-Embassy-Kingston-Rules]]
- [[Gov-Rules/PICA-Jamaica-Passport-Rules]]
- [[Gov-Rules/Compliance-and-Evaluation-Standards]]

## Templates
- [[Templates/Client-Case-Template]]

## Featured Active & Historical Client Dossiers
- [[Clients/C034]] — Active Client Portal Demo (Marcus Campbell, B1/B2)
- [[Clients/C001]] — Approved Case (Gross vs Net JMD Salary Verification)
- [[Clients/C002]] — Refused Case (First-time Applicant + U.S. Fiancée)
- [[Clients/C004]] — Approved Case (Former H-2B + Legally Married/Separated)
""",
    )

    write_vault_note(
        "Gov-Rules/US-Embassy-Kingston-Rules.md",
        """# U.S. Embassy Kingston — Official Visa Rules (2025–2026)

- **Location:** 142 Old Hope Road, Kingston, Jamaica | Tel: `(876) 702-6000`
- **Appointment Portal:** https://ais.usvisa-info.com/en-jm/niv
- **Official Visas Page:** https://jm.usembassy.gov/visas/

## Non-Negotiable Rules
1. **April 1, 2025 DS-160 Barcode Match Rule:** The `AA...` barcode printed on your DS-160 confirmation page MUST exactly match the barcode used on `ais.usvisa-info.com/en-jm/niv` or entry is denied.
2. **RGD 92% Photocopy Rule:** Jamaican RGD birth and marriage certificates are longer than U.S. Letter paper; copies MUST be reduced to **92%** so top and bottom serial numbers remain visible.
3. **2026 MRV Fees:** B1/B2, F-1, J-1 = **$185 USD**; H-2B / petition workers = **$205 USD**; K fiancé(e) = **$265 USD**.
4. **Prohibited Items:** No cellphones, smartwatches, or large bags at 142 Old Hope Road — no storage exists.
5. **Form DS-5535:** Submit ONLY when requested by a Consular Officer (`KingstonNIV@state.gov`, subject `V11 – DS-5535 – [SURNAME, GIVEN NAME]`).

Related: [[Gov-Rules/PICA-Jamaica-Passport-Rules]] | [[Gov-Rules/Compliance-and-Evaluation-Standards]]
""",
    )

    write_vault_note(
        "Gov-Rules/PICA-Jamaica-Passport-Rules.md",
        """# PICA Jamaica — Passport & Civil Document Prerequisites

- **PICA Head Office:** 25C Constant Spring Road, Kingston | Tel: `(876) 754-7422`
- **Online Adult Renewal:** https://passport.pica-online.com/
- **RGD Online Certificates:** https://apps2.rgd.gov.jm/

## Visa-Readiness Checks
- Jamaican passport must have **6+ months validity** past intended U.S. travel date.
- Eligible adults (10-year undamaged passport, no name/marital change) can use **PICA Simplified Adult Renewal Form 1** (included in our Official PDFs viewer).
- Always bring expired passports that contain prior U.S. visas to the Kingston interview.

Related: [[Gov-Rules/US-Embassy-Kingston-Rules]]
""",
    )

    write_vault_note(
        "Gov-Rules/Compliance-and-Evaluation-Standards.md",
        """# JAHTARIA Compliance & Prediction Evaluation Standards

Derived from `JAHTARIA_Visa_Intelligence_Engineer_Package_v01/engineering_handoff.docx`:

1. **Truthful Verification Only:** Never coach concealment, never invent ties, never imply approval guarantees.
2. **Pre-Interview Freeze:** Always freeze ranked question predictions WITH author + timestamp BEFORE the embassy interview. Never retroactively add asked questions as predictions.
3. **Policy vs. Profile Separation:** Track universal policy questions (e.g. `home_country_safety`) separately from profile-driven ranked questions so predictive recall and Precision@5 are never inflated.
4. **Known Data-Quality Traps:**
   - **Gross vs. Net JMD Salary (`C001`):** JMD 116,000 net vs ~JMD 154,875 gross is a legitimate distinction — reconcile clearly rather than assuming misrepresentation.
   - **U.S. Relatives & Fiancé(e) (`C002`, `C004`):** A question about a U.S. partner is not proof of refusal cause; never omit immediate U.S. relatives on DS-160.
   - **Legal Marital Status (`C004`):** Separated applicants without a final Decree Absolute remain legally married.
""",
    )

    write_vault_note(
        "Templates/Client-Case-Template.md",
        """---
case_id: C000
visa_class: B1/B2
stage: new_intake
standing_score: 0
---
# {{case_id}} — Client Dossier

## Verification Checklist
- [ ] Passport validity > 6 months ([[Gov-Rules/PICA-Jamaica-Passport-Rules]])
- [ ] DS-160 AA barcode matches AIS booking ([[Gov-Rules/US-Embassy-Kingston-Rules]])
- [ ] Monthly GROSS vs NET JMD salary verified against payslips
- [ ] Pre-interview predictions frozen before embassy date
""",
    )


def seed_all(db: Session) -> None:
    """Idempotently seed Branding, Users, Taxonomy, 33+1 Cases, Events, Manifest, Gov Sources, PDFs & Obsidian."""

    # 1. Branding Config
    branding = db.query(BrandingConfig).first()
    if not branding:
        branding = BrandingConfig()
        db.add(branding)
        db.commit()

    # 2. Question Taxonomy (20 themes from zip)
    if db.query(QuestionTaxonomy).count() == 0:
        tax_path = SEED_PACKAGE_DIR / "question_taxonomy.csv"
        if tax_path.exists():
            with tax_path.open("r", encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    tid = (row.get("theme_id") or "").strip()
                    if not tid:
                        continue
                    db.add(
                        QuestionTaxonomy(
                            theme_id=tid,
                            sample_question=(row.get("sample_question") or "").strip(),
                            category=(row.get("category") or "travel_or_other").strip(),
                            policy_or_profile_specific=(row.get("policy_or_profile_specific") or "profile_or_standard").strip(),
                        )
                    )
            db.commit()

    # 3. Official Gov Sources (12 verified U.S. & Jamaica agency sources)
    if db.query(GovSource).count() == 0:
        now = datetime.now(timezone.utc)
        for src in OFFICIAL_GOV_SOURCES:
            h = hashlib.sha256(src["verified_summary"].encode("utf-8")).hexdigest()
            db.add(
                GovSource(
                    source_key=src["source_key"],
                    name=src["name"],
                    agency=src["agency"],
                    category=src["category"],
                    url=src["url"],
                    verified_summary=src["verified_summary"],
                    scraped_excerpt=src["verified_summary"],
                    key_rules_json=json.dumps(src["key_rules"]),
                    content_hash=h,
                    scrape_status="verified_seed",
                    last_scraped_at=now,
                    enabled=True,
                )
            )
        db.commit()

    # 4. Official Downloaded PDFs + Default DOCX Blueprint
    if db.query(OfficialDocument).count() == 0:
        for item in OFFICIAL_PDF_CATALOG:
            fpath = OFFICIAL_PDFS_DIR / item["filename"]
            if fpath.exists():
                info = inspect_blueprint_file(fpath)
                db.add(
                    OfficialDocument(
                        doc_key=item["doc_key"],
                        title=item["title"],
                        agency=item["agency"],
                        category=item["category"],
                        filename=item["filename"],
                        file_path=str(fpath),
                        file_format=".pdf",
                        size_bytes=info["size_bytes"],
                        sha256=info["sha256"],
                        source_url=item["source_url"],
                        description=item["description"],
                        detected_fields_json=json.dumps(info["detected_fields"]),
                        is_blueprint=True,
                    )
                )
        bp_docx = _ensure_default_docx_blueprint()
        bp_info = inspect_blueprint_file(bp_docx)
        db.add(
            OfficialDocument(
                doc_key="jahtaria_support_docx_blueprint",
                title="Jahtaria Editable Client Verification & Cover Packet (DOCX Blueprint)",
                agency="Jahtaria Travel Services",
                category="agency_blueprint",
                filename=bp_docx.name,
                file_path=str(bp_docx),
                file_format=".docx",
                size_bytes=bp_info["size_bytes"],
                sha256=bp_info["sha256"],
                source_url="https://jahtariatravelservices.poweredbycyberrock.workers.dev/",
                description="Auto-fillable DOCX template with {{placeholder}} tokens for instant client verification packets.",
                detected_fields_json=json.dumps(bp_info["detected_fields"]),
                is_blueprint=True,
            )
        )
        db.commit()

    # 5. Source Manifest (all 83 inventoried files from zip)
    if db.query(SourceManifestItem).count() == 0:
        man_path = SEED_PACKAGE_DIR / "source_manifest.csv"
        if man_path.exists():
            with man_path.open("r", encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    sid = (row.get("source_id") or "").strip()
                    if not sid:
                        continue
                    db.add(
                        SourceManifestItem(
                            source_id=sid,
                            filename=(row.get("filename") or "").strip(),
                            doc_type=(row.get("type") or "other").strip(),
                            file_format=(row.get("format") or "").strip(),
                            size_bytes=int(row.get("size_bytes") or 0),
                            sha256=(row.get("sha256") or "").strip(),
                            extractable_characters=int(row.get("extractable_characters") or 0),
                            extraction_status=(row.get("extraction_status") or "").strip(),
                            handling=(row.get("handling") or "").strip(),
                            notes=(row.get("notes") or "").strip(),
                        )
                    )
            db.commit()

    # 6. All 33 JAHTARIA Cases + 1 Active Showcase Client (C034)
    if db.query(ClientCase).count() == 0:
        enrichments = {
            "C001": {
                "full_name": "Case C001 (Verified Gross/Net Profile)",
                "parish": "St. Andrew",
                "occupation": "Operations Analyst",
                "employer_name": "Kingston Logistics Ltd.",
                "monthly_gross_jmd": 154875.0,
                "monthly_net_jmd": 116000.0,
                "passport_expiry": "2029-08-14",
                "ds160_confirmation_id": "AA00C001JM",
                "ais_appointment_barcode": "AA00C001JM",
                "intended_travel_date": "2027-02-10",
                "intended_return_date": "2027-02-20",
                "purpose_of_trip": "Short vacation & family visit",
                "us_destination": "Fort Lauderdale, FL",
                "marital_status": "Single",
                "prior_us_refusals": 1,
                "pipeline_stage": "completed",
            },
            "C002": {
                "full_name": "Case C002 (Hospitality & U.S. Partner)",
                "parish": "St. James (Montego Bay)",
                "occupation": "Hotel Front Desk Supervisor",
                "employer_name": "North Coast Resorts",
                "monthly_gross_jmd": 142000.0,
                "monthly_net_jmd": 112000.0,
                "passport_expiry": "2028-11-02",
                "ds160_confirmation_id": "AA00C002JM",
                "ais_appointment_barcode": "AA00C002JM",
                "purpose_of_trip": "Visit fiancée in Florida",
                "us_destination": "Orlando, FL",
                "marital_status": "Single",
                "has_us_relatives": True,
                "us_relatives_details": "U.S. Fiancée (Lawful Permanent Resident, Orlando FL)",
                "pipeline_stage": "completed",
            },
            "C004": {
                "full_name": "Case C004 (Former H-2B / Self-Employed)",
                "parish": "St. Catherine",
                "occupation": "Self-Employed Auto Technician",
                "employer_name": "Independent Workshop",
                "monthly_gross_jmd": 265000.0,
                "monthly_net_jmd": 210000.0,
                "passport_expiry": "2030-03-19",
                "ds160_confirmation_id": "AA00C004JM",
                "ais_appointment_barcode": "AA00C004JM",
                "purpose_of_trip": "Tourism & visiting family",
                "us_destination": "Atlanta, GA",
                "marital_status": "Legally Married - Separated",
                "children_count": 2,
                "has_us_relatives": True,
                "us_relatives_details": "Brother in Georgia (verify DS-160 consistency)",
                "pipeline_stage": "completed",
            },
            "C005": {
                "full_name": "Case C005 (Former F-1 / Customs Officer)",
                "parish": "Kingston",
                "occupation": "Customs Compliance Clerk",
                "employer_name": "Jamaica Customs Agency",
                "monthly_gross_jmd": 195000.0,
                "monthly_net_jmd": 152000.0,
                "passport_expiry": "2027-04-01",
                "ds160_confirmation_id": "AA00C005JM",
                "ais_appointment_barcode": "AA00OLD999",  # Intentional barcode mismatch demo!
                "purpose_of_trip": "Short vacation",
                "us_destination": "New York, NY",
                "prior_us_refusals": 2,
                "pipeline_stage": "risk_audit",
            },
        }

        cases_path = SEED_PACKAGE_DIR / "cases_pseudonymized.jsonl"
        if cases_path.exists():
            for line in cases_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                cid = item["case_id"]
                outcome = item.get("outcome", "unknown")
                default_stage = "completed" if outcome in ("approved", "refused") else "risk_audit"
                extra = enrichments.get(cid, {})
                client = ClientCase(
                    case_id=cid,
                    access_code=f"JAH-{cid}",
                    pseudonym=f"Reference Case {cid}",
                    full_name=extra.get("full_name", f"Reference Case {cid}"),
                    nationality="Jamaica",
                    parish=extra.get("parish", "Kingston & St. Andrew"),
                    visa_class=item.get("visa_class") if item.get("visa_class") != "unknown" else "B1/B2",
                    pipeline_stage=extra.get("pipeline_stage", default_stage),
                    outcome=outcome,
                    outcome_evidence=item.get("outcome_evidence", "user_reported"),
                    passport_number_enc=encrypt_value(f"JM{cid[1:]}8421"),
                    dob_enc=encrypt_value("1991-06-15"),
                    passport_expiry=extra.get("passport_expiry", "2029-05-20" if outcome == "approved" else ""),
                    ds160_confirmation_id=extra.get("ds160_confirmation_id", f"AA00{cid}JM" if outcome != "unknown" else ""),
                    ais_appointment_barcode=extra.get("ais_appointment_barcode", f"AA00{cid}JM" if outcome != "unknown" else ""),
                    intended_travel_date=extra.get("intended_travel_date", "2027-03-15"),
                    intended_return_date=extra.get("intended_return_date", "2027-03-25"),
                    purpose_of_trip=extra.get("purpose_of_trip", ""),
                    us_destination=extra.get("us_destination", ""),
                    occupation=extra.get("occupation", ""),
                    employer_name=extra.get("employer_name", ""),
                    monthly_gross_jmd=extra.get("monthly_gross_jmd"),
                    monthly_net_jmd=extra.get("monthly_net_jmd"),
                    marital_status=extra.get("marital_status", ""),
                    children_count=extra.get("children_count", 0),
                    prior_us_refusals=extra.get("prior_us_refusals", 1 if "previous_refusal" in item.get("profile_tags", []) or "prior_refusal" in item.get("profile_tags", []) else (2 if "multiple_refusals" in item.get("profile_tags", []) else 0)),
                    has_us_relatives=extra.get("has_us_relatives", any("us_" in t for t in item.get("profile_tags", []))),
                    us_relatives_details=extra.get("us_relatives_details", ""),
                    profile_tags_json=json.dumps(item.get("profile_tags", [])),
                    predicted_themes_json=json.dumps(item.get("predicted_question_themes", [])),
                    reported_actual_themes_json=json.dumps(item.get("reported_actual_question_themes", [])),
                    predictions_frozen=bool(item.get("predictions_are_pre_interview", False)),
                    predictions_frozen_at=datetime(2026, 11, 20, 14, 0, tzinfo=timezone.utc) if item.get("predictions_are_pre_interview") else None,
                    predictions_frozen_by="Jahtaria Senior Advisor" if item.get("predictions_are_pre_interview") else "",
                    data_quality=item.get("data_quality", "user_report_only_or_prior_discussion"),
                    open_verification_items=item.get("open_verification_items", ""),
                    consent_status=item.get("consent_to_model_training", "not_documented"),
                    training_eligibility=item.get("training_eligibility", "review_required"),
                )
                db.add(client)
            db.commit()

        # Add C034: Live Active Customer Portal Showcase Case (linked to client@jahtariatravel.com)
        c34 = ClientCase(
            case_id="C034",
            access_code="JAH-C034",
            pseudonym="Marcus Campbell",
            full_name="Marcus Campbell",
            email=SEED_CLIENT_EMAIL,
            phone="+1 (876) 555-0148",
            nationality="Jamaica",
            parish="St. Andrew (Half Way Tree)",
            visa_class="B1/B2",
            pipeline_stage="questionnaire",
            outcome="pending",
            outcome_evidence="in_preparation",
            passport_number_enc=encrypt_value("JM9482710"),
            dob_enc=encrypt_value("1992-08-19"),
            passport_expiry="2030-09-12",
            ds160_confirmation_id="AA00C034JM",
            ais_appointment_barcode="AA00C034JM",
            intended_travel_date="2027-04-12",
            intended_return_date="2027-04-22",
            purpose_of_trip="Attend hospitality trade conference & 5-day family visit",
            us_destination="Miami, FL",
            us_host_contact="Marriott Biscayne Bay / Cousin Andrea Campbell (Miami, FL)",
            occupation="Hospitality Operations Manager",
            employer_name="Blue Mountain Hospitality Group Ltd.",
            monthly_gross_jmd=285000.0,
            monthly_net_jmd=218500.0,
            marital_status="Married",
            children_count=1,
            prior_us_refusals=0,
            has_us_relatives=True,
            us_relatives_details="Cousin (non-immediate relative) in Miami, FL; no immediate relatives (parents/siblings/spouse) in U.S.",
            travel_history_summary="Visited Barbados (2024) and Cayman Islands (2025) for work conferences; returned on time.",
            profile_tags_json=json.dumps(["first_time", "employed", "hospitality", "international_travel", "children_jamaica"]),
            predicted_themes_json=json.dumps(["purpose_of_trip", "employment", "monthly_income", "destination", "children", "travel_history"]),
            data_quality="verified_intake",
            open_verification_items="Confirm signed employer leave letter and 92%-scaled RGD marriage certificate copy before final approval.",
            consent_status="client_portal_active",
            embassy_interview_date="2027-02-18",
            service_package_usd=350.0,
        )
        db.add(c34)
        db.commit()

    # 7. Seed all 37 Interview Events from interview_events.jsonl
    if db.query(InterviewEvent).count() == 0:
        ev_path = SEED_PACKAGE_DIR / "interview_events.jsonl"
        if ev_path.exists():
            for line in ev_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                ev = json.loads(line)
                cid = ev.get("case_id")
                if not db.query(ClientCase).filter(ClientCase.case_id == cid).first():
                    continue
                db.add(
                    InterviewEvent(
                        case_id=cid,
                        event_mode="embassy_reported",
                        sequence=int(ev.get("sequence") or 1),
                        theme=ev.get("theme", "unknown"),
                        question_text=ev.get("sample_paraphrase_not_verbatim", ""),
                        source_type=ev.get("source_type", "user_recollection"),
                        pre_interview_predicted_theme=bool(ev.get("pre_interview_predicted_theme", False)),
                        prediction_classification=ev.get("prediction_classification", "unclassified"),
                        exact_wording_verified=bool(ev.get("exact_question_wording_verified", False)),
                    )
                )
            db.commit()

    # 8. Seed initial Good Standing audits, ranked predictions, journals, facts & approved demo assets for key cases
    if db.query(PipelineJournal).count() == 0:
        all_clients = db.query(ClientCase).all()
        for c in all_clients:
            evaluate_client_standing(db, c)
            generate_ranked_predictions(db, c, author=c.predictions_frozen_by or "system_rules", replace_unfrozen=True)
            db.add(
                PipelineJournal(
                    case_id=c.case_id,
                    event_type="case_ingested",
                    actor="System Seed",
                    summary=f"Initialized case {c.case_id} ({c.visa_class}) with deterministic U.S. Embassy Kingston Good Standing audit ({c.standing_score}%).",
                )
            )
        db.commit()

        # Rich facts & approved deliverables for C034 (so Customer Portal has instant downloadable PDF/PNG!)
        c34 = db.query(ClientCase).filter(ClientCase.case_id == "C034").first()
        if c34:
            for fk, fv, src in [
                ("monthly_gross_jmd", "JMD 285,000", "employer_payslip"),
                ("monthly_net_jmd", "JMD 218,500", "employer_payslip"),
                ("ds160_barcode", "AA00C034JM (Matches AIS)", "ceac_confirmation"),
                ("passport_validity", "Valid until 2030-09-12 (> 6 months)", "pica_passport_scan"),
            ]:
                db.add(ProfileFact(case_id="C034", fact_key=fk, value=fv, as_of_date="2026-11-24", evidence_source=src, confidence="high", conflict_status="verified"))

            p_ws, f_ws = generate_ds160_worksheet_pdf(c34, c34.risk_flags, branding)
            p_chk, f_chk = generate_kingston_checklist_pdf(c34, c34.predictions, branding)
            p_png, f_png = generate_visual_roadmap_png(c34, c34.risk_flags, branding)
            now = datetime.now(timezone.utc)
            db.add(GeneratedAsset(case_id="C034", asset_type="ds160_worksheet_pdf", title="DS-160 Preparation & Verification Worksheet (Approved)", filename=p_ws.name, file_path=str(p_ws), mime_type="application/pdf", filled_fields_json=json.dumps(f_ws), approval_status="approved", approved_by="Staff Specialist", approved_at=now, visible_to_client=True))
            db.add(GeneratedAsset(case_id="C034", asset_type="checklist_pdf", title="U.S. Embassy Kingston Pre-Interview Checklist (Approved)", filename=p_chk.name, file_path=str(p_chk), mime_type="application/pdf", filled_fields_json=json.dumps(f_chk), approval_status="approved", approved_by="Staff Specialist", approved_at=now, visible_to_client=True))
            db.add(GeneratedAsset(case_id="C034", asset_type="visual_roadmap_png", title="Personal Visual Visa Action Roadmap (Approved)", filename=p_png.name, file_path=str(p_png), mime_type="image/png", filled_fields_json=json.dumps(f_png), approval_status="approved", approved_by="Staff Specialist", approved_at=now, visible_to_client=True))
            db.add(PipelineJournal(case_id="C034", event_type="assets_approved", actor="Staff Specialist", summary="Approved DS-160 Worksheet PDF, Kingston Checklist PDF, and Visual Roadmap PNG for client portal download."))
            db.commit()

    # 9. On a brand-new empty database only, seed the initial setup/testing account (`testaccount` / `testpassword`)
    # so you can test all tiers and then change its username & password inside the app before shipping.
    # Once renamed or once any real user exists, it is NEVER re-created on restart.
    if db.query(User).count() == 0:
        db.add(
            User(
                username="testaccount",
                email="testaccount@jahtariatravel.com",
                full_name="Agency Administrator",
                role="ceo",
                all_tiers=True,
                linked_case_id="C034",
                password_hash=hash_password("testpassword"),
                recovery_pin_hash=hash_password("1234"),
                is_active=True,
            )
        )
        db.commit()

    # 9b. Seed default Dual-Mode Gmail Automation & Cron Rules
    if db.query(EmailAutomationRule).count() == 0:
        default_rules = [
            EmailAutomationRule(
                name="Passport Expiring (< 6 Months)",
                description="Automatically emails clients whose Jamaican passport expires within 180 days with PICA Simplified Adult Renewal guidance.",
                rule_type="passport_expiry",
                enabled=True,
                send_mode="auto",
                cron_expr="0 9 * * *",
                interval_minutes=1440,
                cooldown_days=14,
                threshold_days=180,
                subject_template="[{case_id}] Urgent: Jamaican Passport Validity Check ({passport_expiry})",
                body_template=(
                    "Hello {full_name},\n\n"
                    "Our records show your Jamaican passport expires on {passport_expiry}. U.S. Embassy Kingston requires your passport "
                    "to be undamaged and valid for at least 6 months beyond your intended U.S. travel date.\n\n"
                    "Please renew via PICA Simplified Adult Renewal before locking in your appointment, and upload your new passport scan using your portal code {access_code}.\n\n"
                    "Warm regards,\n{agency_name}"
                ),
                use_ai_personalization=True,
            ),
            EmailAutomationRule(
                name="Kingston Embassy Interview Countdown (7 Days)",
                description="Sends pre-interview logistics reminder 7 days before U.S. Embassy Kingston interview (142 Old Hope Rd no-cellphone rule & DS-160/AIS barcode match).",
                rule_type="interview_countdown",
                enabled=True,
                send_mode="auto",
                cron_expr="30 8 * * *",
                interval_minutes=1440,
                cooldown_days=5,
                threshold_days=7,
                subject_template="[{case_id}] Kingston Embassy Interview Reminder ({embassy_interview_date})",
                body_template=(
                    "Hello {full_name},\n\n"
                    "Your U.S. Embassy Kingston interview is scheduled for {embassy_interview_date} at 142 Old Hope Road.\n\n"
                    "Quick Kingston Checklist:\n"
                    "- Confirm your DS-160 AA-barcode ({ds160_confirmation_id}) matches your AIS appointment profile\n"
                    "- Bring one 2x2 white-background photo (no glasses) and 92%-scaled RGD certificate copies\n"
                    "- Leave cellphones, smartwatches, and large bags outside (no storage at Embassy)\n\n"
                    "Warm regards,\n{agency_name}"
                ),
                use_ai_personalization=True,
            ),
            EmailAutomationRule(
                name="Unresolved Red Risk Flags & Missing Docs",
                description="Queues a tailored staff-approved email listing unresolved RED flags and missing supporting documents.",
                rule_type="missing_docs_red_flags",
                enabled=True,
                send_mode="approval",
                cron_expr="0 10 */2 * *",
                interval_minutes=2880,
                cooldown_days=10,
                threshold_days=30,
                subject_template="[{case_id}] Action Needed: Items to Clear Before Your U.S. Visa Interview",
                body_template=(
                    "Hello {full_name},\n\n"
                    "Our Consular Audit ({standing_score}% Good Standing) flagged priority items to verify before your appointment:\n"
                    "{red_flags}\n\n"
                    "Please reply with the requested documents or sign into your client portal with code {access_code}.\n\n"
                    "Warm regards,\n{agency_name}"
                ),
                use_ai_personalization=True,
            ),
            EmailAutomationRule(
                name="Unanswered Questionnaire Nudge",
                description="Automatically nudges clients who still have pending verification questions in their Client Portal.",
                rule_type="questionnaire_nudge",
                enabled=True,
                send_mode="auto",
                cron_expr="0 11 */3 * *",
                interval_minutes=4320,
                cooldown_days=7,
                threshold_days=30,
                subject_template="[{case_id}] Quick Reminder: {unanswered_count} Verification Question(s) Waiting",
                body_template=(
                    "Hello {full_name},\n\n"
                    "You have {unanswered_count} quick follow-up verification question(s) waiting in your Jahtaria Client Portal.\n"
                    "Sign in anytime using your Case Code: {access_code}\n\n"
                    "Warm regards,\n{agency_name}"
                ),
                use_ai_personalization=False,
            ),
            EmailAutomationRule(
                name="Autonomous Consular AI Outreach (Dual Mode)",
                description="Consular AI scans every active client profile daily and drafts bespoke outreach for the Approval Queue whenever it spots a risk or deadline.",
                rule_type="ai_autonomous",
                enabled=True,
                send_mode="approval",
                cron_expr="0 10 * * *",
                interval_minutes=1440,
                cooldown_days=14,
                threshold_days=180,
                subject_template="[{case_id}] Personal Visa Readiness Check-In",
                body_template="",
                use_ai_personalization=True,
            ),
        ]
        db.add_all(default_rules)
        db.commit()

    # 10. Seed Obsidian Vault Notes + Engineer Package Reference + Featured Client Dossiers
    _seed_obsidian_vault()
    ref_note_path = OBSIDIAN_VAULT_DIR / "Reference" / "JAHTARIA_Engineer_Package_v01.md"
    if not ref_note_path.exists():
        readme_txt = (SEED_PACKAGE_DIR / "README.md").read_text(encoding="utf-8", errors="ignore") if (SEED_PACKAGE_DIR / "README.md").exists() else ""
        handoff_paras: list[str] = []
        handoff_doc = SEED_PACKAGE_DIR / "engineering_handoff.docx"
        if handoff_doc.exists():
            try:
                doc = DocxDocument(str(handoff_doc))
                handoff_paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()][:80]
            except Exception:
                pass
        body = (
            "# JAHTARIA Visa Intelligence Engineer Package v01 (Bundled Reference)\n\n"
            "All 8 raw reference files are bundled in `seed_package/` and indexed live in SQLite (`clients`, `interview_events`, `question_taxonomy`, `source_manifest`) for future data ingestion, prediction recall, and audit benchmarking.\n\n"
            "## Package README\n\n"
            + readme_txt
            + ("\n\n## Engineering Handoff Excerpt\n\n" + "\n\n".join(handoff_paras) if handoff_paras else "")
        )
        write_vault_note("Reference/JAHTARIA_Engineer_Package_v01.md", body)
    for cid in ("C001", "C002", "C004", "C034"):
        client = db.query(ClientCase).filter(ClientCase.case_id == cid).first()
        if client and not (OBSIDIAN_VAULT_DIR / "Clients" / f"{cid}.md").exists():
            sync_client_to_obsidian(client, client.risk_flags, client.journal_entries)


def reset_seed_clients_to_pristine(db: Session) -> dict[str, int]:
    """Restore the unchanged pristine seeded clients (C001-C034), events, facts & assets while preserving API keys and GovSources."""
    from app.models import ClientDocument, InterviewPrediction, RiskFlag

    # Delete existing client rows cleanly (cascades risk_flags, predictions, facts, interview_events, journals, assets, documents)
    removed = db.query(ClientCase).count()
    for c in db.query(ClientCase).all():
        db.delete(c)
    db.query(InterviewEvent).delete()
    db.query(PipelineJournal).delete()
    db.query(ProfileFact).delete()
    db.query(RiskFlag).delete()
    db.query(InterviewPrediction).delete()
    db.query(GeneratedAsset).delete()
    db.query(ClientDocument).delete()
    db.commit()

    seed_all(db)
    restored = db.query(ClientCase).count()
    return {"removed_previous": removed, "restored_pristine_clients": restored}
