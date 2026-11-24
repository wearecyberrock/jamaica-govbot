# Jahtaria Travel Services — U.S. Visa Intelligence & Document Automation Suite

A commercial, white-labelable **Desktop-first** (and VPS/Docker-ready) AI U.S. Visa Preparation, Good Standing Risk Engine, Official PDF/Blueprint Automation, and Consular Interview Intelligence platform built for Jamaican travel & visa agencies.

---

## Quick Start (Desktop — Zero Docker Required)

### macOS / Linux
```bash
git clone https://github.com/wearecyberrock/jamaica-govbot.git
cd jamaica-govbot
./start.sh
```

### Windows
Double-click **`start.bat`** (or run `start.bat` from Command Prompt).

### Electron Native Desktop App (Commercial Packaging)
```bash
cd desktop
npm install
npm start            # Launches local FastAPI + Next.js inside native desktop window
# npm run dist:mac   # Build macOS DMG
# npm run dist:win   # Build Windows NSIS installer
# npm run dist:linux # Build Linux AppImage
```

---

## Seeded Role Accounts (3 Dedicated Dashboards)

Open **`http://localhost:3010/login`** (1-click local desktop sign-in buttons are included on the login screen):

| Role | Dashboard Route | Email | Password |
| :--- | :--- | :--- | :--- |
| **CEO Executive Suite** | `/ceo` | `ceo@jahtariatravel.com` | `JahtariaCEO2026!` |
| **Staff Case Workspace** | `/staff` | `staff@jahtariatravel.com` | `JahtariaStaff2026!` |
| **Customer Portal** | `/portal` | `client@jahtariatravel.com` | `JahtariaClient2026!` |

* **New Customers** can self-register via **New Client Signup** OR sign in with a **Case Access Code** (e.g., `JAH-C034`, `JAH-C001`).

---

## What's Inside

1. **Three Role-Based Dashboards (Jamaican / Jahtaria Theme + White-Label Resale Controls):**
   * **Customer Portal (`/portal`):** AI Visa Q&A Assistant with clickable official citations, live Good Standing readiness bar, guided intake form & follow-up questionnaire, practice mock interview simulator, and advisor-approved downloadable PDFs & Visual Action Roadmap PNG.
   * **Staff Operations Workspace (`/staff`):** Kanban & Table Client Pipeline (seeded with all **33 cases** from `JAHTARIA_Visa_Intelligence_Engineer_Package_v01` + active showcase case `C034`), 6-tab Client Deep-Dive (Good Standing Bar, Encrypted Intake & Questionnaire, Pre-Interview Prediction Freeze + Mock Simulator + Outcome Recorder, Blueprint Auto-Fill + Human Approval Gate, Chronological Pipeline Journal, and **Hermes Autonomous Agent Console**).
   * **CEO Executive Suite (`/ceo`):** Agency KPIs, estimated USD pipeline value, compliant Prediction Evaluation (separating profile-driven thematic recall from universal mandatory policy questions like `home_country_safety`), top denial-risk flags, Team Login management, and 60-second **White-Label Agency Branding** customization.

2. **Database Window, Scraped Official Gov Sources & Embedded Official PDF Viewer:**
   * **11 Real Downloaded Official Government PDFs** visible inline right inside the dashboard:
     * PICA Jamaica Passport Application Form (Adult & Minor)
     * PICA Simplified Adult Passport Renewal Form (Form 1) + Official Instruction Sheet
     * PICA Statutory Declaration Form & Citizenship by Descent Form
     * U.S. Dept. of State **Form DS-5535** (Supplemental Questions — 221(g)), **DS-157**, and **DS-156E**
     * RGD Jamaica Birth Certificate Certified Copy Application (`BIRREQ`)
     * Embassy of Jamaica Passport Renewal & Birth Certificate Guidelines
   * **12 Official Government Reference Sources** (`jm.usembassy.gov/visas/`, April 1, 2025 DS-160 AA-Barcode Rule, `travel.state.gov` KNG-Kingston Post Supplement & 92% RGD Photocopy Rule, MRV Fees, `ais.usvisa-info.com/en-jm/niv`, `ceac.state.gov`, `pica.gov.jm`, `nira.gov.jm`) with clickable links, SHA-256 hashing, live Refresh/Scrape, and change-diff alerts.
   * **Clean Interactive Table Explorer:** Browse all 11 database tables (`clients`, `source_manifest` [all 83 inventoried files], `question_taxonomy`, `interview_events`, `gov_sources`, `official_documents`, etc.) + CSV/Google Sheet batch importer.

3. **Integrated Obsidian Vault (`data/obsidian-vault/`):**
   * Browse, search, edit Markdown notes with clickable `[[wikilinks]]` and backlinks inside Staff/CEO dashboards, auto-sync client dossiers & journals (`Clients/C034.md`), or open the exact folder directly in Obsidian Desktop.

4. **Hermes Multi-Provider AI, Subscriptions, Composio & Built-in `/mcp` Server:**
   * Easy Setup hub supporting **Antigravity (`agy` CLI)**, **Local Ollama** (100% private PII mode), **OpenAI/ChatGPT**, **Anthropic/Claude**, **Google Gemini**, **xAI Grok**, and **OpenRouter** (encrypted via Fernet).
   * **Composio OAuth Hub** for Gmail, Google Sheets, Google Docs, Microsoft 365, and external Company DBs.
   * **Built-in `/mcp` Streamable HTTP Endpoint** (`http://localhost:8010/mcp`) so Claude Desktop, ChatGPT Connectors, Antigravity, or Assimilis can drive Jahtaria tools directly using your existing subscriptions.

---

## Future VPS Deployment (Docker + PostgreSQL/pgvector)
When ready to host on a Linux VPS:
```bash
cp .env.example .env
docker compose up -d --build
```
