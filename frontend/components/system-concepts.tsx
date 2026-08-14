"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  ApiError,
  assignConcept,
  createConcept,
  getConcepts,
  getSystemConcepts,
  unassignConcept,
} from "@/lib/api";
import type { Concept, ConceptAssignment } from "@/lib/types";

// Konzept-Zuordnung als toggelbare Chips im System-Detail.
// Zugeordnet: gefüllt (manual = violett, heuristic = cyan, mit Match-Grund).
// Nicht zugeordnet: gestrichelter Rahmen. Klick toggelt (POST manual / DELETE).
export function SystemConcepts({ systemId }: { systemId: number }) {
  const [allConcepts, setAllConcepts] = useState<Concept[]>([]);
  const [assignments, setAssignments] = useState<
    Map<number, ConceptAssignment>
  >(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [reasonHint, setReasonHint] = useState<{
    name: string;
    reason: string;
  } | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [conceptsRes, systemConcepts] = await Promise.all([
        getConcepts(),
        getSystemConcepts(systemId),
      ]);
      const map = new Map<number, ConceptAssignment>();
      for (const a of systemConcepts.items) map.set(a.concept_id, a);
      setAllConcepts(conceptsRes.items);
      setAssignments(map);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 0
            ? "Backend nicht erreichbar."
            : err.message
          : err instanceof Error
            ? err.message
            : "Konzepte konnten nicht geladen werden.",
      );
    } finally {
      setLoading(false);
    }
  }, [systemId]);

  useEffect(() => {
    setLoading(true);
    void load();
  }, [load]);

  const toggle = useCallback(
    async (concept: Concept) => {
      const assigned = assignments.has(concept.id);
      setBusyId(concept.id);
      setError(null);
      try {
        if (assigned) {
          await unassignConcept(systemId, concept.id);
        } else {
          await assignConcept(systemId, concept.id);
        }
        await load();
      } catch (err) {
        setError(
          err instanceof ApiError
            ? err.message
            : assigned
              ? "Entfernen fehlgeschlagen."
              : "Zuordnen fehlgeschlagen.",
        );
      } finally {
        setBusyId(null);
      }
    },
    [assignments, systemId, load],
  );

  const handleCreate = useCallback(async () => {
    const name = newName.trim();
    if (!name || creating) return;
    setCreating(true);
    setError(null);
    try {
      const concept = await createConcept(name);
      await assignConcept(systemId, concept.id);
      setNewName("");
      await load();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Konzept konnte nicht angelegt werden.",
      );
    } finally {
      setCreating(false);
    }
  }, [newName, creating, systemId, load]);

  const hasHeuristic = useMemo(
    () => [...assignments.values()].some((a) => a.source === "heuristic"),
    [assignments],
  );

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-zinc-500">
        <Loader2 className="size-4 animate-spin" />
        Konzepte werden geladen…
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Chips */}
      <div className="flex flex-wrap items-center gap-2">
        {allConcepts.length === 0 ? (
          <span className="text-sm text-zinc-500">
            Noch keine Konzepte vorhanden.
          </span>
        ) : (
          allConcepts.map((c) => {
            const assignment = assignments.get(c.id);
            const assigned = assignment !== undefined;
            const heuristic = assignment?.source === "heuristic";
            const busy = busyId === c.id;
            const reason = assignment?.match_reason ?? null;
            return (
              <button
                key={c.id}
                type="button"
                onClick={() => void toggle(c)}
                disabled={busy}
                title={
                  heuristic && reason
                    ? `Heuristik-Treffer: ${reason}`
                    : assigned
                      ? "Zugeordnet — klicken zum Entfernen"
                      : "Klicken zum Zuordnen"
                }
                onMouseEnter={() =>
                  heuristic && reason
                    ? setReasonHint({ name: c.name, reason })
                    : undefined
                }
                onMouseLeave={() =>
                  setReasonHint((prev) =>
                    prev && prev.name === c.name ? null : prev,
                  )
                }
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                  "disabled:cursor-wait disabled:opacity-60",
                  assigned
                    ? heuristic
                      ? "border-cyan-500/40 bg-cyan-500/15 text-cyan-200 hover:bg-cyan-500/25"
                      : "border-violet-500/40 bg-violet-500/15 text-violet-200 hover:bg-violet-500/25"
                    : "border-dashed border-zinc-700 bg-transparent text-zinc-400 hover:border-zinc-500 hover:text-zinc-200",
                )}
              >
                {busy ? <Loader2 className="size-3 animate-spin" /> : null}
                {c.name}
                {heuristic ? (
                  <span
                    aria-hidden
                    className="rounded-sm bg-cyan-500/20 px-1 text-[0.6rem] uppercase tracking-wide text-cyan-300"
                  >
                    auto
                  </span>
                ) : null}
              </button>
            );
          })
        )}
      </div>

      {/* Match-Grund-Detail (bei Hover eines Heuristik-Chips) */}
      {reasonHint ? (
        <p className="text-xs text-cyan-300/80">
          <span className="font-medium">{reasonHint.name}</span> — Match-Grund:{" "}
          <span className="font-mono">{reasonHint.reason}</span>
        </p>
      ) : null}

      {/* Inline-Neuanlage */}
      <div className="flex items-center gap-2">
        <Input
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void handleCreate();
            }
          }}
          placeholder="Neues Konzept…"
          autoComplete="off"
          disabled={creating}
          className="h-8 w-56 text-xs"
        />
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={creating || newName.trim().length === 0}
          onClick={() => void handleCreate()}
          className="h-8 border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
        >
          {creating ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Plus className="size-3.5" />
          )}
          Anlegen &amp; zuordnen
        </Button>
      </div>

      {/* Legende */}
      <div className="flex flex-wrap items-center gap-4 text-[0.7rem] text-zinc-500">
        <span className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-full border border-violet-500/40 bg-violet-500/30" />
          manuell zugeordnet
        </span>
        {hasHeuristic ? (
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-full border border-cyan-500/40 bg-cyan-500/30" />
            heuristisch (auto) — Grund im Tooltip
          </span>
        ) : null}
        <span className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-full border border-dashed border-zinc-600" />
          nicht zugeordnet
        </span>
      </div>

      {error ? <p className="text-xs text-red-400">{error}</p> : null}
    </div>
  );
}
