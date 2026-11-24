"use client";

import { useEffect, useState } from "react";
import { BookOpen, FileText, Plus, Save, Search, Link2, FolderOpen } from "lucide-react";
import { apiFetch } from "@/lib/api";
import type { VaultNoteMeta } from "@/lib/types";

interface NoteDetail {
  path: string;
  name: string;
  content: string;
  links: string[];
  backlinks: string[];
  updated_at: string;
  vault_dir: string;
}

export function ObsidianVaultView() {
  const [vaultDir, setVaultDir] = useState("");
  const [notes, setNotes] = useState<VaultNoteMeta[]>([]);
  const [query, setQuery] = useState("");
  const [activeNote, setActiveNote] = useState<NoteDetail | null>(null);
  const [draftContent, setDraftContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [newPath, setNewPath] = useState("");

  const loadNotes = async (q = "") => {
    const res = await apiFetch<{ vault_dir: string; notes: VaultNoteMeta[] }>(
      `/api/obsidian/notes?query=${encodeURIComponent(q)}`
    );
    setVaultDir(res.vault_dir);
    setNotes(res.notes);
    if (!activeNote && res.notes.length > 0) {
      openNote(res.notes.find((n) => n.path === "Index.md")?.path || res.notes[0].path);
    }
  };

  const openNote = async (path: string) => {
    try {
      const note = await apiFetch<NoteDetail>(`/api/obsidian/note?path=${encodeURIComponent(path)}`);
      setActiveNote(note);
      setDraftContent(note.content);
      setStatusMsg("");
    } catch {
      setStatusMsg(`Linked note '${path}' does not exist yet — create it below.`);
    }
  };

  const saveNote = async () => {
    if (!activeNote) return;
    setSaving(true);
    try {
      const saved = await apiFetch<NoteDetail>("/api/obsidian/note", {
        method: "PUT",
        body: JSON.stringify({ path: activeNote.path, content: draftContent }),
      });
      setActiveNote(saved);
      setStatusMsg("Saved to local Obsidian vault folder.");
      await loadNotes(query);
    } finally {
      setSaving(false);
    }
  };

  const createNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPath.trim()) return;
    const saved = await apiFetch<NoteDetail>("/api/obsidian/note", {
      method: "PUT",
      body: JSON.stringify({
        path: newPath.trim(),
        content: `# ${newPath.trim().replace(".md", "").split("/").pop()}\n\nLinked: [[Index]]\n\n`,
      }),
    });
    setNewPath("");
    setActiveNote(saved);
    setDraftContent(saved.content);
    await loadNotes(query);
  };

  useEffect(() => {
    loadNotes(query).catch(() => {});
  }, [query]);

  return (
    <div className="space-y-4">
      <div className="ja-card p-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-extrabold text-ja-green flex items-center gap-2">
            <BookOpen className="w-5 h-5" /> Integrated Obsidian Knowledge &amp; Client Dossier Vault
          </h2>
          <p className="text-xs text-slate-600 flex items-center gap-1.5 mt-0.5">
            <FolderOpen className="w-3.5 h-3.5 text-ja-navy" /> Local Obsidian Folder: <code>{vaultDir || "data/obsidian-vault"}</code> (open directly in Obsidian Desktop too!)
          </p>
        </div>
        <form onSubmit={createNote} className="flex items-center gap-2">
          <input
            className="ja-input w-56 text-xs"
            placeholder="New note (e.g. Notes/Embassy-Tips)"
            value={newPath}
            onChange={(e) => setNewPath(e.target.value)}
          />
          <button type="submit" className="ja-btn-primary px-3 py-2 text-xs inline-flex items-center gap-1">
            <Plus className="w-3.5 h-3.5" /> New Note
          </button>
        </form>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Left Sidebar: File Tree */}
        <div className="lg:col-span-4 ja-card p-4 space-y-3 max-h-[680px] overflow-y-auto">
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              className="ja-input pl-9 text-xs"
              placeholder="Search notes, [[links]], #tags..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            {notes.map((n) => (
              <button
                key={n.path}
                onClick={() => openNote(n.path)}
                className={`w-full text-left p-2.5 rounded-xl border transition ${
                  activeNote?.path === n.path
                    ? "bg-ja-greenLight border-ja-green"
                    : "bg-white border-slate-100 hover:border-slate-300"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-bold text-xs text-slate-900 flex items-center gap-1.5 truncate">
                    <FileText className="w-3.5 h-3.5 text-ja-green shrink-0" />
                    {n.path}
                  </span>
                  <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-slate-100 text-slate-500">
                    {n.folder}
                  </span>
                </div>
                <p className="text-[11px] text-slate-500 mt-1 line-clamp-1">{n.excerpt}</p>
              </button>
            ))}
          </div>
        </div>

        {/* Right Pane: Editor & Wikilink Graph */}
        <div className="lg:col-span-8 ja-card p-4 flex flex-col gap-3">
          {activeNote ? (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-3">
                <div>
                  <h3 className="font-extrabold text-base text-ja-green">{activeNote.path}</h3>
                  {statusMsg && <p className="text-xs font-bold text-emerald-700">{statusMsg}</p>}
                </div>
                <button
                  onClick={saveNote}
                  disabled={saving}
                  className="ja-btn-primary px-4 py-2 text-xs inline-flex items-center gap-1.5"
                >
                  <Save className="w-4 h-4" /> {saving ? "Saving..." : "Save Note"}
                </button>
              </div>

              <textarea
                value={draftContent}
                onChange={(e) => setDraftContent(e.target.value)}
                className="ja-input font-mono text-xs leading-relaxed min-h-[420px] flex-1"
              />

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2 border-t text-xs">
                <div>
                  <div className="font-bold text-ja-navy flex items-center gap-1 mb-1.5">
                    <Link2 className="w-3.5 h-3.5" /> Outgoing [[Wikilinks]] ({activeNote.links.length})
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {activeNote.links.map((lnk, idx) => (
                      <button
                        key={idx}
                        onClick={() => openNote(lnk.endsWith(".md") ? lnk : `${lnk}.md`)}
                        className="px-2 py-1 rounded-lg bg-ja-greenLight text-ja-green font-bold hover:bg-ja-green hover:text-white transition"
                      >
                        [[{lnk}]]
                      </button>
                    ))}
                    {activeNote.links.length === 0 && <span className="text-slate-400">No outgoing links</span>}
                  </div>
                </div>
                <div>
                  <div className="font-bold text-ja-navy flex items-center gap-1 mb-1.5">
                    <Link2 className="w-3.5 h-3.5" /> Backlinks ({activeNote.backlinks.length})
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {activeNote.backlinks.map((b) => (
                      <button
                        key={b}
                        onClick={() => openNote(b)}
                        className="px-2 py-1 rounded-lg bg-slate-100 text-slate-700 font-bold hover:bg-ja-navy hover:text-white transition"
                      >
                        {b}
                      </button>
                    ))}
                    {activeNote.backlinks.length === 0 && <span className="text-slate-400">No backlinks yet</span>}
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="p-12 text-center text-sm text-slate-400">Select a Markdown note from the vault.</div>
          )}
        </div>
      </div>
    </div>
  );
}
