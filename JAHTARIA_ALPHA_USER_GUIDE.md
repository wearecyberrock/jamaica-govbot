# Jahtaria Visa Intelligence Alpha (v2.3.0) — Complete User Guide

Welcome to **Jahtaria Visa Intelligence Alpha**, your standalone Windows desktop platform for **Jamaican U.S. Visa Preparation, Consular Risk Audits, Document Automation, and Autonomous Gmail Outreach** — built specifically around U.S. Embassy Kingston (142 Old Hope Road), PICA, and Jamaican RGD rules.

> **Truthfulness & Compliance Policy:** This software helps agencies and clients prepare **accurate, truthful, well-documented** visa applications and interview readiness. It never fabricates documents, never coaches concealment, and never guarantees visa approval.

---

## 1. Installation & First-Time Launch

1. Double-click **`Jahtaria-Visa-Intelligence-Alpha-Setup-2.3.0.exe`** and follow the Windows installer prompts (zero Python, Node.js, or Docker required).
2. Open **Jahtaria Visa Intelligence Alpha** from your Desktop or Start Menu.
3. All your client data, encrypted PII (passport numbers & DOBs), uploaded documents, and API keys stay **100% private and encrypted locally** on your PC (`%APPDATA%\jahtaria-visa-desktop\data\`).

---

## 2. Signing In & Securing Your Production Account

### Initial Setup Login (All-Tier Preview)
On a brand-new installation, a single starter account is included so you can test every role before going live:
- **Username:** `testaccount`
- **Password:** `testpassword`
- **Offline Recovery PIN:** `1234`

While signed in as `testaccount`, a **`CEO | Staff | Client`** switcher appears in the top bar so you can preview all three portals:
- **CEO (`/ceo`):** Full executive analytics, approval rates, prediction recall, team account management, white-label branding, bulk data tools, and all Staff tools.
- **Staff (`/staff`):** Daily case management, client audits, questionnaires, document vault/studio, Gmail automation, and official government forms.
- **Client Portal (`/portal`):** Applicant self-service view (Good Standing score, interactive questionnaire, voice/text mock Embassy interview, and Staff-approved downloadable deliverables).

### Switching to Your Real Owner Credentials (Recommended Before Live Use)
1. Click the **Key icon (🔑)** next to Sign Out in the bottom-left sidebar.
2. Enter your **Current Password** (`testpassword`), set your **new Username** (e.g., `jahtaria_ceo`), your **new Password**, and a **4–8 digit Recovery PIN**.
3. Click **Save Changes**.
   - As soon as you rename `testaccount`, the test tier-switcher disappears automatically, and `testaccount` will **never** be recreated on restart — your installation is now locked to your private CEO account.

### Forgot Password (Works Even Offline!)
- On the Sign-In screen, click **Forgot password?**, type your **Username**, and reset using:
  1. Your **Offline Recovery PIN** (works 100% locally, no internet or email needed), **OR**
  2. A **6-digit reset code emailed via Gmail** (if Gmail is connected and your account has a recovery email), **OR**
  3. **CEO Reset:** The CEO can reset any Staff or Client password anytime under **Team & Staff → Reset PW**.

### Creating Staff & Client Accounts
- **CEO → Team & Staff:** Create Staff or Client accounts using a **Username**, Password, and Recovery PIN (email optional).
- **Client Self-Signup / Case Code:** Clients can register on the **Client Sign Up** tab or jump straight into their case on the **Case Code** tab using their personal code (e.g. `JAH-C034`).

---

## 3. Connecting AI Models & Using the Smart Auto Picker

Open **AI, Voice & Setup** in the left sidebar (or simply **paste an API key directly into chat**!).

### Smart Auto Picker & Flagship Models
Click the model dropdown inside the chat input bar:
- **`★ Auto · Best Flagship` (Recommended):** Always sits at #1 — automatically picks your best healthy connected flagship model and fails over cleanly if a provider experiences temporary high demand (HTTP 503/429).
- **Live Auto-Discovery:** Automatically fetches the latest flagship models from every connected provider (`gemini-4-neon`, `gemini-4-hydrogen`, `gemini-4-carbon`, `claude-opus-5-5`, `claude-sonnet-5-5`, `gpt-5.4`, `o3`, `grok-4`, local Ollama models, etc.).
- **Refresh Live Models & Custom Model ID:** In **AI, Voice & Setup → Section 5**, click **Refresh Live Models** anytime or type any brand-new model ID into the **Custom Model ID** box and click **Use Model**.

### Fast Connection Options
- **Smart Paste in Chat:** Paste any Gemini (`AIza...`), OpenAI (`sk-...`), Anthropic (`sk-ant-...`), Grok (`xai-...`), or OpenRouter (`sk-or-v1-...`) key straight into chat. The app encrypts it at rest, masks it from chat history, and activates it automatically (with 1-click **Undo**).
- **Subscriptions:** Sign in via OAuth for **ChatGPT / Codex**, **Claude Pro/Max**, or **Antigravity (Google OAuth / local CLI)**.
- **100% Offline Private Mode:** Run **Local Ollama** on your PC so sensitive client PII never leaves your computer.

---

## 4. Gmail Automation, Cron Reminders & Google App Passwords

Click **Gmail & Cron** in the left sidebar to open the full Email & Scheduler Hub.

### What Is a "Google App Password" (and How to Get One in 60 Seconds)?
Google blocks desktop apps from using your normal Gmail login password for security. A **Google App Password** is a free, official **16-character passcode** created inside your Google Account specifically for one app:
1. Go to **[myaccount.google.com/security](https://myaccount.google.com/security)** and make sure **2-Step Verification** is turned **ON**.
2. Search for **"App passwords"** in the top search bar (or visit `myaccount.google.com/apppasswords`).
3. Type app name **`Jahtaria Visa Alpha`** and click **Create**.
4. Copy the 16-character code Google shows (e.g., `abcd efgh ijkl mnop`).
5. In the app, go to **Gmail & Cron → Connection**, enter your Gmail address and paste that 16-character App Password, click **Save Gmail Config**, then click **Test SMTP & IMAP**.

*(Before connecting Gmail, the app runs safely in **Dry-Run Preview Mode** — you can test rules, inspect AI-drafted emails, and use **Copy for WhatsApp** without sending anything live!)*

### Three Automation Modes (Dual Mode Is Default)
- **Dual Mode (Recommended):** Routine reminders (passport expiring `< 6 months`, Kingston interview `7-day` countdown, unanswered questionnaire nudges) **send automatically on schedule**, while sensitive or AI-initiated outreach (unresolved red flags, custom campaigns) waits in your **Approval Queue** for 1-click review & send.
- **Full Autopilot:** All enabled rules send automatically on schedule.
- **Approval Queue Only:** Every scheduled message is drafted and held until a staff member clicks **Approve & Send**.

### Built-In Cron Scheduler + Chat Cron Commands (Just Like Hermes Cron!)
A built-in background cron scheduler runs automatically while the app is open, and you can also click **Sync Hermes Cron** to export CLI jobs (`hermes_cron_jobs.json`).

**Create & manage cron jobs naturally right in chat:**
- *"Create a daily 9am cron to email clients whose passport expires within 180 days"*
- *"Schedule a weekly Monday 8am reminder for clients with upcoming Kingston interviews"*
- *"Email C034 about her passport expiring and 92% RGD copies"*
- *"List cron jobs"* | *"Pause cron #3"* | *"Enable cron #3"* | *"Delete cron #5"*
- *"Run email cron"* | *"Poll inbox"*

### Automatic Safety & Productivity Features
- **Anti-Spam Cooldowns:** Each rule tracks when a client was last emailed (e.g., max once every 14 days for passport expiry) so clients are never spammed.
- **Per-Client Pause Switch:** Mute automatic emails for any individual client under **Gmail & Cron → Connection**.
- **Inbox-to-Vault Attachment Sync (IMAP):** Click **Poll Inbox → Vault** (or leave auto-poll ON every 15 min) — when a client emails back a passport photo, payslip, or PDF, the app automatically matches their email, logs the reply, saves every attachment into their **Client Vault**, and runs AI OCR!
- **1-Click Copy for WhatsApp:** Every queued, drafted, sent, or received message has a **Copy WhatsApp** button formatted cleanly for WhatsApp messaging.

---

## 5. What Are Composio, ClawLink & MCP?

Open **AI, Voice & Setup** to connect external agency tools:
- **Composio:** One-click OAuth bridge that lets the agent connect to **Gmail**, **Google Sheets**, **Google Docs**, **Microsoft 365 (Word/OneDrive)**, and **HubSpot CRM** without setting up developer credentials. Just paste your Composio API key (`ak_...`) in chat or Settings and toggle apps ON.
- **ClawLink:** Remote workspace & gateway bridge — paste your ClawLink URL + Bearer token in chat or Settings to connect remote agent workflows.
- **MCP (Model Context Protocol):**
  - **Inbound (`/mcp`):** Your app exposes **11 live tools** at `http://127.0.0.1:8010/mcp` so external AI apps (Antigravity, Claude Desktop, ChatGPT) can query clients, run audits, and fill forms directly. Copy or export the JSON snippet in **Settings → Section 7**.
  - **Outbound MCP:** Paste any external MCP server URL (`https://.../mcp`) or `{"mcpServers": {...}}` JSON directly into chat to auto-register and probe its tools.

---

## 6. Clients, Active Clients & Reference Data Package

### Bundled Reference Data (`JAHTARIA_Visa_Intelligence_Engineer_Package_v01`)
All 8 raw files from the Engineering Package (`cases_pseudonymized.jsonl/.csv`, `interview_events.jsonl`, `question_taxonomy.csv`, `source_manifest.json/.csv`, `engineering_handoff.docx`, and `README.md`) are **permanently bundled inside the installer** and automatically indexed into:
- **34 Pristine Cases (`C001–C034`)** powering Good Standing risk scoring and **CEO Analytics** (approval rates & pre-interview prediction recall).
- **37 Reported Kingston Interview Events** & **Question Taxonomy** powering ranked interview predictions.
- **83 Source Manifest Entries** (searchable in **Database → `source_manifest`**).
- **Obsidian Vault Reference Note** (`Reference/JAHTARIA_Engineer_Package_v01.md`) so your team and the AI agent can reference the exact schema for all future data added.

### Working with Active Clients (Left Sidebar)
- **Active Clients** starts clean/blank on launch.
- Click any client from **Clients** (`Active`, `Historical`, or `All`), **Spreadsheet**, **CEO Analytics**, or **Gmail** to add them to your **Active Clients** sidebar list for fast switching.
- Click the small **`×`** beside any client in the sidebar to remove them from your active working list anytime.

---

## 7. Smart Paste, Universal ZIP/File Client Synthesizer & Safe Chat Delete

You can drop files directly into the chat window (or press `Ctrl+V` to paste screenshots/images):
- **ZIP Archives (`.zip`):** Unpacks the archive, reads `.csv`, `.xlsx`, `.txt`, `.md`, `.json`, `.docx`, and `.pdf` files inside, uses AI to **synthesize all new clients**, matches client documents by name, and shows a **Confirm & Apply** card (creating every client + attaching their files straight into their Vault!).
- **Spreadsheets & Text Lists (`.csv`, `.xlsx`, `.txt`, `.md`, `.json`):** Auto-extracts multiple new client profiles behind a **Confirm & Apply** card with **1-click Undo**.
- **Single Client Documents & Images (`.pdf`, `.png`, `.jpg`, `.docx`):** Saves to the selected client's Vault, runs AI Vision/OCR to read passport dates/salaries/names, and offers 1-click field updates.
- **Official Website URLs:** Paste any official link (e.g., `https://jis.gov.jm/`) in chat to add it to **Gov Sources** and live-scrape it immediately.
- **Natural-Language Client Edits & Safe Deletes (with Undo!):**
  - *"Add new client Keisha Grant, B1/B2, Kingston, salary 280000"*
  - *"Update C034 gross salary to 310000"*
  - *"Delete client C034"* | *"Delete all reference cases"* | *"Delete all clients"* (CEO only) | *"Restore pristine seed data"*
  - Every write/delete shows a **Confirm & Apply** preview card and saves a snapshot for **1-click Undo**.

---

## 8. Document Vault, 92% RGD Converter, Full-Screen Signature Studio & Questionnaires

- **Per-Client Document Vault:** Organized into `Passport / ID`, `Financial & Payslips`, `RGD Civil`, `Embassy Forms`, and `Photos / Other`.
- **1-Click 92% RGD Photocopy Converter:** Automatically scales Jamaican RGD birth/marriage certificates to **92%** on U.S. Letter paper so top/bottom serial numbers are never clipped at U.S. Embassy Kingston.
- **AI Fill Official PDFs:** Auto-populates official government forms (PICA Passport Renewal, DS-5535, DS-157, DS-156E, RGD BIRREQ) from client data.
- **Full-Screen Document & Signature Studio:** Click **Edit & Sign Full Screen** on any PDF, image, or DOCX to add draggable text boxes, checkmarks, date stamps, drawn/typed signatures, or edit DOCX text inline — saves a **new version** while keeping original files untouched.
- **1-Click Embassy Packet Export:** Exports a merged PDF or ZIP bundle of all client documents ready for Kingston interview day.
- **Interactive Questionnaires (Unlimited):** Click **Import into Chat** from any client's Intake tab (or ask in chat *"generate 25 follow-up questions for C034"*). Includes **💡 Tips & Explanations**, **Multiple Choice**, custom answers, and **+ Add More** (up to 1,000 per batch, infinitely repeatable).

---

## 9. Resizing & Productivity Tips

- **Drag Panel Dividers:** Drag the vertical divider next to the left sidebar or right side panel to resize freely (double-click any divider to reset; widths persist automatically).
- **Full-Screen Side Panel:** Click the **Maximize** icon in the top-right corner of any side panel to inspect Spreadsheets, PDFs, or Analytics full-screen.
- **Voice Mode & Mock Interviews:** Click the **Mic** icon to talk hands-free or toggle **Voice** in the top bar (works with free built-in Edge Neural Voices, ElevenLabs, or Fish Audio).
- **Local Folder Access:** Use the top menu **Jahtaria Alpha → Open Local Data & PDFs Folder** or **Open Obsidian Vault Folder** anytime.
