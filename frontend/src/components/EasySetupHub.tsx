"use client";

import { useEffect, useState } from "react";
import {
  Cpu,
  Plug,
  Server,
  Palette,
  CheckCircle2,
  Copy,
  Plus,
  Trash2,
  Upload,
  Database,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import type { BrandingConfig } from "@/lib/types";

interface SetupHubData {
  ai_providers: {
    active_provider: string;
    active_model: string;
    subscriptions: {
      antigravity_agy: { installed: boolean; binary: string; models: string[] };
      claude_cli: { installed: boolean; binary: string };
      codex_chatgpt_cli: { installed: boolean; binary: string };
    };
    ollama: { reachable: boolean; base_url: string; models: string[] };
    api_keys: Record<string, boolean>;
  };
  composio: {
    api_key_configured: boolean;
    api_key_masked: string;
    apps: Array<{ app_id: string; name: string; description: string; connected: boolean; account_label: string }>;
  };
  company_db_url: string;
  mcp_servers: Array<{ name: string; url: string; transport: string; enabled: boolean }>;
  inbound_mcp_endpoint: string;
  claude_desktop_snippet: string;
}

export function EasySetupHub({
  isCeo,
  branding,
  onBrandingUpdated,
}: {
  isCeo: boolean;
  branding: BrandingConfig | null;
  onBrandingUpdated?: (b: BrandingConfig) => void;
}) {
  const [hub, setHub] = useState<SetupHubData | null>(null);
  const [provider, setProvider] = useState("auto");
  const [model, setModel] = useState("gpt-4o-mini");
  const [ollamaUrl, setOllamaUrl] = useState("http://localhost:11434");
  const [ollamaModel, setOllamaModel] = useState("llama3.2");
  const [openaiKey, setOpenaiKey] = useState("");
  const [anthropicKey, setAnthropicKey] = useState("");
  const [geminiKey, setGeminiKey] = useState("");
  const [xaiKey, setXaiKey] = useState("");
  const [openrouterKey, setOpenrouterKey] = useState("");
  const [aiStatus, setAiStatus] = useState("");

  const [composioKey, setComposioKey] = useState("");
  const [companyDbUrl, setCompanyDbUrl] = useState("");
  const [dbTestMsg, setDbTestMsg] = useState("");

  const [mcpList, setMcpList] = useState<Array<{ name: string; url: string; transport: string; enabled: boolean }>>([]);
  const [newMcpName, setNewMcpName] = useState("");
  const [newMcpUrl, setNewMcpUrl] = useState("");
  const [newMcpTransport, setNewMcpTransport] = useState("streamable_http");
  const [mcpMsg, setMcpMsg] = useState("");

  // White-label branding fields (CEO only)
  const [agencyName, setAgencyName] = useState(branding?.agency_name || "Jahtaria Travel Services");
  const [tagline, setTagline] = useState(branding?.tagline || "");
  const [contactEmail, setContactEmail] = useState(branding?.contact_email || "");
  const [whatsapp, setWhatsapp] = useState(branding?.whatsapp_number || "");
  const [brandMsg, setBrandMsg] = useState("");

  const loadHub = async () => {
    const data = await apiFetch<SetupHubData>("/api/settings/setup-hub");
    setHub(data);
    setProvider(data.ai_providers.active_provider || "auto");
    setModel(data.ai_providers.active_model || "gpt-4o-mini");
    setOllamaUrl(data.ai_providers.ollama.base_url || "http://localhost:11434");
    setCompanyDbUrl(data.company_db_url || "");
    setMcpList(data.mcp_servers || []);
  };

  useEffect(() => {
    loadHub().catch(() => {});
  }, []);

  const saveAi = async (e: React.FormEvent) => {
    e.preventDefault();
    await apiFetch("/api/settings/ai-provider", {
      method: "POST",
      body: JSON.stringify({
        ai_provider: provider,
        ai_model: model,
        ollama_base_url: ollamaUrl,
        ollama_model: ollamaModel,
        openai_api_key: openaiKey || undefined,
        anthropic_api_key: anthropicKey || undefined,
        gemini_api_key: geminiKey || undefined,
        xai_api_key: xaiKey || undefined,
        openrouter_api_key: openrouterKey || undefined,
      }),
    });
    setAiStatus("Saved encrypted AI provider settings.");
    setOpenaiKey("");
    setAnthropicKey("");
    setGeminiKey("");
    setXaiKey("");
    setOpenrouterKey("");
    await loadHub();
  };

  const testAi = async () => {
    const res = await apiFetch<{ provider_used: string; reply: string }>("/api/settings/test-ai", { method: "POST" });
    setAiStatus(`[${res.provider_used}] ${res.reply}`);
  };

  const saveComposioKey = async () => {
    await apiFetch("/api/settings/composio", { method: "POST", body: JSON.stringify({ api_key: composioKey }) });
    setComposioKey("");
    await loadHub();
  };

  const toggleApp = async (appId: string, connected: boolean) => {
    await apiFetch("/api/settings/composio", {
      method: "POST",
      body: JSON.stringify({ toggle_app_id: appId, connected }),
    });
    await loadHub();
  };

  const testDb = async () => {
    const res = await apiFetch<{ ok: boolean; table_count?: number; error?: string }>("/api/settings/company-db/test", {
      method: "POST",
      body: JSON.stringify({ company_db_url: companyDbUrl }),
    });
    setDbTestMsg(res.ok ? `Connected! Found ${res.table_count} table(s).` : `Error: ${res.error}`);
  };

  const addMcp = async () => {
    if (!newMcpName.trim() || !newMcpUrl.trim()) return;
    const updated = [...mcpList, { name: newMcpName.trim(), url: newMcpUrl.trim(), transport: newMcpTransport, enabled: true }];
    await apiFetch("/api/settings/mcp-servers", { method: "POST", body: JSON.stringify(updated) });
    setMcpList(updated);
    setNewMcpName("");
    setNewMcpUrl("");
    setMcpMsg("Saved MCP server.");
  };

  const removeMcp = async (idx: number) => {
    const updated = mcpList.filter((_, i) => i !== idx);
    await apiFetch("/api/settings/mcp-servers", { method: "POST", body: JSON.stringify(updated) });
    setMcpList(updated);
  };

  const testMcp = async (url: string, transport: string) => {
    const res = await apiFetch<{ ok: boolean; tool_count?: number; error?: string }>("/api/settings/mcp-servers/test", {
      method: "POST",
      body: JSON.stringify({ url, transport }),
    });
    setMcpMsg(res.ok ? `MCP reachable (${res.tool_count ?? 0} tools).` : `MCP probe failed: ${res.error}`);
  };

  const saveBranding = async (e: React.FormEvent) => {
    e.preventDefault();
    const updated = await apiFetch<BrandingConfig>("/api/ceo/branding", {
      method: "PUT",
      body: JSON.stringify({
        agency_name: agencyName,
        tagline,
        contact_email: contactEmail,
        whatsapp_number: whatsapp,
      }),
    });
    setBrandMsg("White-label branding updated across all portals.");
    onBrandingUpdated?.(updated);
  };

  const uploadLogo = async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    await apiFetch("/api/ceo/branding/logo", { method: "POST", body: fd });
    setBrandMsg("Logo uploaded! Refresh to see across all tabs.");
  };

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-extrabold text-ja-green">Easy Setup, Hermes AI Subscriptions, Connectors &amp; MCP Hub</h2>
        <p className="text-xs text-slate-600">
          All keys are encrypted at rest with Fernet AES-128. Connect Antigravity, Ollama, Claude, ChatGPT, Grok, Composio (Gmail/Sheets/Docs), Company DB, and MCP servers in minutes.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* CARD 1: HERMES AI ENGINE & SUBSCRIPTIONS */}
        <form onSubmit={saveAi} className="ja-card p-5 space-y-3.5">
          <div className="flex items-center justify-between border-b pb-2.5">
            <h3 className="font-extrabold text-sm text-ja-green flex items-center gap-2">
              <Cpu className="w-4 h-4" /> 1. Hermes AI Engine &amp; Subscriptions
            </h3>
            <button type="button" onClick={testAi} className="px-3 py-1 rounded-lg bg-ja-greenLight text-ja-green text-xs font-bold hover:bg-ja-green hover:text-white transition">
              Test Connection
            </button>
          </div>

          <div className="grid grid-cols-3 gap-2 text-[11px]">
            <div className="p-2 rounded-xl bg-slate-50 border">
              <div className="font-bold text-slate-700">Antigravity (`agy`)</div>
              <div className={hub?.ai_providers.subscriptions.antigravity_agy.installed ? "text-emerald-700 font-bold" : "text-slate-500"}>
                {hub?.ai_providers.subscriptions.antigravity_agy.installed ? "Detected" : "CLI Optional"}
              </div>
            </div>
            <div className="p-2 rounded-xl bg-slate-50 border">
              <div className="font-bold text-slate-700">Local Ollama</div>
              <div className={hub?.ai_providers.ollama.reachable ? "text-emerald-700 font-bold" : "text-slate-500"}>
                {hub?.ai_providers.ollama.reachable ? `${hub.ai_providers.ollama.models.length} model(s)` : "Not running"}
              </div>
            </div>
            <div className="p-2 rounded-xl bg-slate-50 border">
              <div className="font-bold text-slate-700">Claude / ChatGPT</div>
              <div className="text-ja-navy font-bold">API or /mcp</div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2.5">
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Active Provider</label>
              <select className="ja-input" value={provider} onChange={(e) => setProvider(e.target.value)}>
                <option value="auto">Auto (Ollama → API Keys → Grounded)</option>
                <option value="antigravity">Antigravity Subscription (`agy` CLI)</option>
                <option value="ollama">Local Ollama (100% Private PII)</option>
                <option value="openai">OpenAI / ChatGPT API</option>
                <option value="anthropic">Anthropic / Claude API</option>
                <option value="gemini">Google Gemini API</option>
                <option value="xai_grok">xAI Grok API</option>
                <option value="openrouter">OpenRouter</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Active Model ID</label>
              <input className="ja-input" value={model} onChange={(e) => setModel(e.target.value)} placeholder="gpt-4o-mini / claude-3-5-sonnet-latest" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2.5">
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Ollama Base URL</label>
              <input className="ja-input" value={ollamaUrl} onChange={(e) => setOllamaUrl(e.target.value)} />
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Ollama Model</label>
              <input className="ja-input" value={ollamaModel} onChange={(e) => setOllamaModel(e.target.value)} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <input className="ja-input text-xs" type="password" placeholder={`OpenAI Key ${hub?.ai_providers.api_keys.openai ? "(Configured)" : ""}`} value={openaiKey} onChange={(e) => setOpenaiKey(e.target.value)} />
            <input className="ja-input text-xs" type="password" placeholder={`Anthropic Key ${hub?.ai_providers.api_keys.anthropic ? "(Configured)" : ""}`} value={anthropicKey} onChange={(e) => setAnthropicKey(e.target.value)} />
            <input className="ja-input text-xs" type="password" placeholder={`Gemini Key ${hub?.ai_providers.api_keys.gemini ? "(Configured)" : ""}`} value={geminiKey} onChange={(e) => setGeminiKey(e.target.value)} />
            <input className="ja-input text-xs" type="password" placeholder={`xAI Grok Key ${hub?.ai_providers.api_keys.xai_grok ? "(Configured)" : ""}`} value={xaiKey} onChange={(e) => setXaiKey(e.target.value)} />
          </div>
          <input className="ja-input text-xs" type="password" placeholder={`OpenRouter Key ${hub?.ai_providers.api_keys.openrouter ? "(Configured)" : ""}`} value={openrouterKey} onChange={(e) => setOpenrouterKey(e.target.value)} />

          {aiStatus && <div className="text-xs font-semibold text-ja-navy bg-blue-50 border border-blue-200 rounded-lg p-2.5">{aiStatus}</div>}

          <button type="submit" className="ja-btn-primary w-full py-2 text-xs">
            Save Encrypted AI Settings
          </button>
        </form>

        {/* CARD 2: COMPOSIO OAUTH (GMAIL, SHEETS, DOCS, MS365) & COMPANY DB */}
        <div className="ja-card p-5 space-y-4">
          <div className="border-b pb-2.5">
            <h3 className="font-extrabold text-sm text-ja-green flex items-center gap-2">
              <Plug className="w-4 h-4" /> 2. Composio Apps (Gmail, Sheets, Docs, MS 365) &amp; Company DB
            </h3>
          </div>

          <div className="flex gap-2">
            <input
              className="ja-input text-xs"
              type="password"
              placeholder={hub?.composio.api_key_configured ? `Composio Key (${hub.composio.api_key_masked})` : "Paste Composio API Key"}
              value={composioKey}
              onChange={(e) => setComposioKey(e.target.value)}
            />
            <button onClick={saveComposioKey} className="ja-btn-primary px-4 text-xs shrink-0">
              Save Key
            </button>
          </div>

          <div className="space-y-2">
            {hub?.composio.apps.map((app) => (
              <div key={app.app_id} className="flex items-center justify-between gap-2 p-2.5 rounded-xl border bg-slate-50/70">
                <div>
                  <div className="font-bold text-xs text-slate-900">{app.name}</div>
                  <div className="text-[11px] text-slate-500">{app.description}</div>
                </div>
                <button
                  onClick={() => toggleApp(app.app_id, !app.connected)}
                  className={`px-3 py-1 rounded-lg text-xs font-bold shrink-0 transition ${
                    app.connected
                      ? "bg-emerald-100 text-emerald-800 border border-emerald-200"
                      : "bg-white border border-slate-300 text-slate-700 hover:bg-ja-green hover:text-white"
                  }`}
                >
                  {app.connected ? "Connected" : "Connect"}
                </button>
              </div>
            ))}
          </div>

          <div className="pt-2 border-t space-y-2">
            <div className="text-xs font-bold text-ja-navy flex items-center gap-1.5">
              <Database className="w-3.5 h-3.5" /> External Company Database URL (Postgres / MySQL / SQLite)
            </div>
            <div className="flex gap-2">
              <input
                className="ja-input text-xs"
                placeholder="postgresql://user:pass@host:5432/company_crm"
                value={companyDbUrl}
                onChange={(e) => setCompanyDbUrl(e.target.value)}
              />
              <button onClick={testDb} className="px-3 py-2 rounded-lg bg-ja-navy text-white text-xs font-bold shrink-0">
                Test &amp; Save
              </button>
            </div>
            {dbTestMsg && <p className="text-xs font-bold text-ja-green">{dbTestMsg}</p>}
          </div>
        </div>

        {/* CARD 3: MCP SERVER HUB (INBOUND /mcp + OUTBOUND SERVERS) */}
        <div className="ja-card p-5 space-y-3.5">
          <div className="border-b pb-2.5">
            <h3 className="font-extrabold text-sm text-ja-green flex items-center gap-2">
              <Server className="w-4 h-4" /> 3. MCP Hub — Use Your Claude, ChatGPT &amp; Antigravity Subscriptions
            </h3>
          </div>

          <div className="p-3 rounded-xl bg-ja-greenLight border border-ja-green/20 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-extrabold text-ja-green">Built-in Inbound MCP Server Endpoint</span>
              <button
                onClick={() => navigator.clipboard?.writeText(hub?.claude_desktop_snippet || "")}
                className="text-[11px] font-bold text-ja-navy inline-flex items-center gap-1 hover:underline"
              >
                <Copy className="w-3 h-3" /> Copy Claude/ChatGPT Config
              </button>
            </div>
            <code className="block text-xs bg-white px-2.5 py-1.5 rounded border text-ja-navy font-bold">
              {hub?.inbound_mcp_endpoint || "http://localhost:8010/mcp"}
            </code>
            <pre className="text-[10px] bg-slate-900 text-emerald-300 p-2.5 rounded-lg overflow-x-auto">
              {hub?.claude_desktop_snippet}
            </pre>
          </div>

          <div className="space-y-2">
            <div className="text-xs font-bold text-slate-700">External MCP Servers (Streamable HTTP / SSE)</div>
            {mcpList.map((m, i) => (
              <div key={i} className="flex items-center justify-between gap-2 p-2 rounded-xl border bg-white text-xs">
                <div className="truncate">
                  <span className="font-bold">{m.name}</span>{" "}
                  <span className="text-slate-500">({m.transport}) — {m.url}</span>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <button onClick={() => testMcp(m.url, m.transport)} className="px-2 py-1 rounded bg-slate-100 hover:bg-ja-navy hover:text-white font-bold">
                    Test
                  </button>
                  <button onClick={() => removeMcp(i)} className="p-1 text-red-600 hover:bg-red-50 rounded">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}
            <div className="grid grid-cols-12 gap-2">
              <input className="ja-input col-span-3 text-xs" placeholder="Name" value={newMcpName} onChange={(e) => setNewMcpName(e.target.value)} />
              <input className="ja-input col-span-5 text-xs" placeholder="https://mcp.server/mcp" value={newMcpUrl} onChange={(e) => setNewMcpUrl(e.target.value)} />
              <select className="ja-input col-span-2 text-xs" value={newMcpTransport} onChange={(e) => setNewMcpTransport(e.target.value)}>
                <option value="streamable_http">HTTP</option>
                <option value="sse">SSE</option>
              </select>
              <button onClick={addMcp} className="ja-btn-primary col-span-2 text-xs inline-flex items-center justify-center">
                <Plus className="w-4 h-4" />
              </button>
            </div>
            {mcpMsg && <p className="text-xs font-bold text-ja-navy">{mcpMsg}</p>}
          </div>
        </div>

        {/* CARD 4: WHITE-LABEL COMMERCIAL BRANDING (CEO RESALE CONTROL) */}
        <form onSubmit={saveBranding} className="ja-card p-5 space-y-3.5">
          <div className="border-b pb-2.5">
            <h3 className="font-extrabold text-sm text-ja-green flex items-center gap-2">
              <Palette className="w-4 h-4" /> 4. Commercial White-Label Branding {isCeo ? "(CEO Control)" : "(View Only)"}
            </h3>
            <p className="text-[11px] text-slate-500">
              Resell this software to any travel/visa agency in 60 seconds — customize Agency Name, Tagline, Contact &amp; Logo.
            </p>
          </div>

          <div className="space-y-2.5">
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Agency Display Name</label>
              <input className="ja-input" disabled={!isCeo} value={agencyName} onChange={(e) => setAgencyName(e.target.value)} />
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Tagline</label>
              <input className="ja-input" disabled={!isCeo} value={tagline} onChange={(e) => setTagline(e.target.value)} />
            </div>
            <div className="grid grid-cols-2 gap-2.5">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Support Email</label>
                <input className="ja-input" disabled={!isCeo} value={contactEmail} onChange={(e) => setContactEmail(e.target.value)} />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">WhatsApp Number</label>
                <input className="ja-input" disabled={!isCeo} value={whatsapp} onChange={(e) => setWhatsapp(e.target.value)} />
              </div>
            </div>
            {isCeo && (
              <div className="pt-1">
                <label className="block text-xs font-bold text-slate-700 mb-1 flex items-center gap-1">
                  <Upload className="w-3.5 h-3.5" /> Replace Agency Logo (PNG/JPG)
                </label>
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => e.target.files?.[0] && uploadLogo(e.target.files[0])}
                  className="block w-full text-xs text-slate-600 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-ja-greenLight file:text-ja-green file:font-bold"
                />
              </div>
            )}
          </div>

          {brandMsg && (
            <div className="text-xs font-bold text-emerald-700 flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4" /> {brandMsg}
            </div>
          )}

          {isCeo && (
            <button type="submit" className="ja-btn-primary w-full py-2 text-xs">
              Save White-Label Branding
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
