"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Check,
  Grid3x3,
  Loader2,
  RotateCw,
  ServerCrash,
  Sparkles,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  ConceptGraph,
  ConceptGraphLegend,
} from "@/components/concept-graph";
import { ApiError, assignConcept, autoAssignConcepts, getConceptGraph } from "@/lib/api";
import type {
  AutoAssignAssignment,
  ConceptGraph as ConceptGraphData,
} from "@/lib/types";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; graph: ConceptGraphData }
  | { status: "error"; message: string; offline: boolean };

function proposalKey(p: AutoAssignAssignment): string {
  return `${p.system_id}-${p.concept_id}`;
}

function apiMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    return err.status === 0 ? "Backend nicht erreichbar." : err.message;
  }
  return err instanceof Error ? err.message : fallback;
}

export default function ConceptsPage() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [previewing, setPreviewing] = useState(false);
  const [applyingAll, setApplyingAll] = useState(false);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [proposals, setProposals] = useState<AutoAssignAssignment[] | null>(
    null,
  );
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (initial = false) => {
    if (initial) setState({ status: "loading" });
    try {
      const graph = await getConceptGraph(false);
      setState({ status: "ready", graph });
    } catch (err) {
      const offline = err instanceof ApiError && err.status === 0;
      const message =
        err instanceof ApiError
          ? offline
            ? "Backend nicht erreichbar. Läuft der API-Server?"
            : err.message
          : err instanceof Error
            ? err.message
            : "Unbekannter Fehler beim Laden.";
      setState({ status: "error", message, offline });
    }
  }, []);

  useEffect(() => {
    void load(true);
  }, [load]);

  // T13: Vorschau (dry_run) — berechnet Vorschläge, persistiert nichts.
  const runPreview = useCallback(async () => {
    setPreviewing(true);
    setError(null);
    setNotice(null);
    try {
      const res = await autoAssignConcepts(true);
      setProposals(res.assignments);
      if (res.assignments.length === 0) {
        setNotice(
          "Keine neuen Vorschläge — alle heuristischen Treffer sind bereits zugeordnet.",
        );
      }
    } catch (err) {
      setError(apiMessage(err, "Vorschau fehlgeschlagen."));
    } finally {
      setPreviewing(false);
    }
  }, []);

  // Einzelnen Vorschlag übernehmen: als bestätigte Heuristik-Kante persistieren
  // (source='heuristic' + match_reason), damit die Herkunft erhalten bleibt.
  const confirmOne = useCallback(
    async (p: AutoAssignAssignment) => {
      if (p.system_id == null || p.concept_id == null) return;
      const key = proposalKey(p);
      setBusyKey(key);
      setError(null);
      try {
        await assignConcept(p.system_id, p.concept_id, {
          source: "heuristic",
          matchReason: p.reason ?? null,
        });
        setProposals((prev) =>
          prev ? prev.filter((x) => proposalKey(x) !== key) : prev,
        );
        await load(false);
      } catch (err) {
        setError(apiMessage(err, "Übernehmen fehlgeschlagen."));
      } finally {
        setBusyKey(null);
      }
    },
    [load],
  );

  const discardOne = useCallback((p: AutoAssignAssignment) => {
    const key = proposalKey(p);
    setProposals((prev) =>
      prev ? prev.filter((x) => proposalKey(x) !== key) : prev,
    );
  }, []);

  // Alle übernehmen: echter Auto-Assign-Lauf (ohne dry_run) — einfach & konsistent.
  const confirmAll = useCallback(async () => {
    setApplyingAll(true);
    setError(null);
    setNotice(null);
    try {
      const res = await autoAssignConcepts(false);
      setNotice(
        `${res.created} Zuordnung(en) übernommen, ${res.skipped_existing} bereits vorhanden.`,
      );
      setProposals(null);
      await load(false);
    } catch (err) {
      setError(apiMessage(err, "Auto-Assign fehlgeschlagen."));
    } finally {
      setApplyingAll(false);
    }
  }, [load]);

  const hasEdges = state.status === "ready" && state.graph.links.length > 0;
  const busy = previewing || applyingAll;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <span className="text-xs font-medium uppercase tracking-[0.35em] text-zinc-500">
            Hadrian³
          </span>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-50">
            Konzepte
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            Welche Systeme welche Marktkonzepte nutzen — bipartiter Graph.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            render={<Link href="/concepts/matrix" />}
            variant="outline"
            className="border-zinc-700 bg-zinc-900 text-zinc-300 hover:bg-zinc-800"
          >
            <Grid3x3 className="size-4" />
            Matrix
          </Button>
          {hasEdges ? (
            <Button
              variant="outline"
              onClick={() => void runPreview()}
              disabled={busy}
              className="border-zinc-700 bg-zinc-900 text-zinc-300 hover:bg-zinc-800"
            >
              {previewing ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Sparkles className="size-4" />
              )}
              Vorschau
            </Button>
          ) : null}
        </div>
      </header>

      {notice ? (
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-2.5 text-sm text-emerald-300">
          {notice}
        </div>
      ) : null}
      {error ? (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm text-red-300">
          {error}
        </div>
      ) : null}

      {/* T13: Vorschau-Liste der Heuristik-Vorschläge */}
      {proposals && proposals.length > 0 ? (
        <div className="flex flex-col gap-3 rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-zinc-200">
                {proposals.length} Vorschlag(e) — nichts wurde bisher
                gespeichert
              </p>
              <p className="mt-0.5 text-xs text-zinc-500">
                Übernommene Vorschläge werden als heuristische Kante (auto)
                gespeichert.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                onClick={() => void confirmAll()}
                disabled={busy || busyKey !== null}
                className="bg-zinc-100 text-zinc-900 hover:bg-white"
              >
                {applyingAll ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Check className="size-3.5" />
                )}
                Alle übernehmen
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setProposals(null)}
                disabled={busy || busyKey !== null}
                className="text-zinc-400 hover:text-zinc-200"
              >
                Schließen
              </Button>
            </div>
          </div>

          <ul className="flex flex-col divide-y divide-zinc-800/70">
            {proposals.map((p) => {
              const key = proposalKey(p);
              const rowBusy = busyKey === key;
              return (
                <li
                  key={key}
                  className="flex flex-wrap items-center justify-between gap-3 py-2.5"
                >
                  <div className="min-w-0">
                    <span className="font-mono text-sm text-zinc-100">
                      {p.system}
                    </span>
                    <span className="mx-2 text-zinc-600">→</span>
                    <span className="text-sm text-cyan-200">{p.concept}</span>
                    {p.reason ? (
                      <span className="ml-2 font-mono text-xs text-zinc-500">
                        {p.reason}
                      </span>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Button
                      size="xs"
                      variant="outline"
                      onClick={() => void confirmOne(p)}
                      disabled={rowBusy || applyingAll}
                      className="border-cyan-500/40 bg-cyan-500/10 text-cyan-200 hover:bg-cyan-500/20"
                    >
                      {rowBusy ? (
                        <Loader2 className="size-3 animate-spin" />
                      ) : (
                        <Check className="size-3" />
                      )}
                      Übernehmen
                    </Button>
                    <Button
                      size="xs"
                      variant="ghost"
                      onClick={() => discardOne(p)}
                      disabled={rowBusy || applyingAll}
                      className="text-zinc-500 hover:text-zinc-300"
                    >
                      <X className="size-3" />
                      Verwerfen
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      {state.status === "loading" ? (
        <div className="flex items-center justify-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/30 py-24 text-sm text-zinc-500">
          <Loader2 className="size-4 animate-spin" />
          Graph wird geladen…
        </div>
      ) : null}

      {state.status === "error" ? (
        <div className="flex flex-col items-center justify-center gap-4 rounded-lg border border-zinc-800 bg-zinc-900/30 px-6 py-20 text-center">
          <span className="flex size-12 items-center justify-center rounded-full border border-zinc-800 bg-zinc-950 text-zinc-400">
            {state.offline ? (
              <ServerCrash className="size-6" />
            ) : (
              <AlertTriangle className="size-6" />
            )}
          </span>
          <div>
            <p className="text-sm font-medium text-zinc-200">
              Graph konnte nicht geladen werden
            </p>
            <p className="mt-1 max-w-md text-sm text-zinc-500">
              {state.message}
            </p>
          </div>
          <Button
            variant="outline"
            onClick={() => void load(true)}
            className="border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
          >
            <RotateCw className="size-4" />
            Erneut versuchen
          </Button>
        </div>
      ) : null}

      {state.status === "ready" ? (
        hasEdges ? (
          <div className="flex flex-col gap-3">
            <ConceptGraphLegend />
            <ConceptGraph data={state.graph} />
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center gap-4 rounded-lg border border-dashed border-zinc-800 bg-zinc-900/20 px-6 py-20 text-center">
            <span className="flex size-12 items-center justify-center rounded-full border border-zinc-800 bg-zinc-950 text-violet-400">
              <Sparkles className="size-6" />
            </span>
            <div>
              <p className="text-sm font-medium text-zinc-300">
                Noch keine Zuordnungen
              </p>
              <p className="mt-1 max-w-md text-sm text-zinc-500">
                Konzepte sind noch keinem System zugeordnet. Die Vorschau
                leitet Zuordnungen aus Prefix (VP → Volume Profile) und
                Regeltexten ab — du bestätigst sie einzeln oder alle.
              </p>
            </div>
            <Button
              onClick={() => void runPreview()}
              disabled={busy}
              className="bg-zinc-100 text-zinc-900 hover:bg-white"
            >
              {previewing ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Sparkles className="size-4" />
              )}
              Vorschau anzeigen
            </Button>
          </div>
        )
      ) : null}
    </div>
  );
}
