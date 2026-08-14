"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  Loader2,
  RotateCw,
  ServerCrash,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  ApiError,
  assignConcept,
  getConceptGraph,
  getConcepts,
  getSystems,
  unassignConcept,
} from "@/lib/api";
import type { Concept, SystemSummary } from "@/lib/types";

type EdgeSource = "manual" | "heuristic";

interface MatrixData {
  systems: SystemSummary[];
  concepts: Concept[];
  edges: Map<string, EdgeSource>; // key = `${systemId}:${conceptId}`
}

type LoadState =
  | { status: "loading" }
  | { status: "ready"; data: MatrixData }
  | { status: "error"; message: string; offline: boolean };

function edgeKey(systemId: number, conceptId: number): string {
  return `${systemId}:${conceptId}`;
}

// "system:7" -> 7
function idFromNode(node: string): number {
  return Number.parseInt(node.slice(node.indexOf(":") + 1), 10);
}

export default function ConceptMatrixPage() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [filter, setFilter] = useState("");
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (initial = false) => {
    if (initial) setState({ status: "loading" });
    try {
      const [systemsRes, conceptsRes, graph] = await Promise.all([
        getSystems(),
        getConcepts(),
        // include_unlinked_systems egal: wir brauchen nur die Kanten.
        getConceptGraph(true),
      ]);
      const edges = new Map<string, EdgeSource>();
      for (const link of graph.links) {
        const sid = idFromNode(link.source);
        const cid = idFromNode(link.target);
        edges.set(edgeKey(sid, cid), link.assignment_source);
      }
      const systems = [...systemsRes.items].sort((a, b) =>
        a.name.localeCompare(b.name),
      );
      const concepts = [...conceptsRes.items].sort((a, b) =>
        a.name.localeCompare(b.name),
      );
      setState({ status: "ready", data: { systems, concepts, edges } });
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

  const toggle = useCallback(
    async (systemId: number, conceptId: number) => {
      if (state.status !== "ready") return;
      const key = edgeKey(systemId, conceptId);
      const current = state.data.edges.get(key);
      setBusyKey(key);
      setError(null);
      try {
        if (current) {
          await unassignConcept(systemId, conceptId);
        } else {
          await assignConcept(systemId, conceptId);
        }
        setState((prev) => {
          if (prev.status !== "ready") return prev;
          const edges = new Map(prev.data.edges);
          if (current) edges.delete(key);
          else edges.set(key, "manual");
          return { ...prev, data: { ...prev.data, edges } };
        });
      } catch (err) {
        setError(
          err instanceof ApiError
            ? err.message
            : current
              ? "Entfernen fehlgeschlagen."
              : "Zuordnen fehlgeschlagen.",
        );
      } finally {
        setBusyKey(null);
      }
    },
    [state],
  );

  const filteredSystems = useMemo(() => {
    if (state.status !== "ready") return [];
    const q = filter.trim().toLowerCase();
    if (!q) return state.data.systems;
    return state.data.systems.filter((s) =>
      s.name.toLowerCase().includes(q),
    );
  }, [state, filter]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <span className="text-xs font-medium uppercase tracking-[0.35em] text-zinc-500">
            Hadrian³
          </span>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-50">
            Konzept-Matrix
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            System × Konzept — Zelle klicken zum Zuordnen/Entfernen.
          </p>
        </div>
        <Button
          render={<Link href="/concepts" />}
          variant="outline"
          className="border-zinc-700 bg-zinc-900 text-zinc-300 hover:bg-zinc-800"
        >
          <ArrowLeft className="size-4" />
          Zum Graph
        </Button>
      </header>

      {error ? (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm text-red-300">
          {error}
        </div>
      ) : null}

      {state.status === "loading" ? (
        <div className="flex items-center justify-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/30 py-24 text-sm text-zinc-500">
          <Loader2 className="size-4 animate-spin" />
          Matrix wird geladen…
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
              Matrix konnte nicht geladen werden
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
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Systeme filtern…"
              autoComplete="off"
              className="h-8 w-64 text-xs"
            />
            <div className="flex flex-wrap items-center gap-4 text-[0.7rem] text-zinc-500">
              <span className="inline-flex items-center gap-1.5">
                <span className="size-2.5 rounded-sm border border-violet-500/40 bg-violet-500/30" />
                manuell
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="size-2.5 rounded-sm border border-cyan-500/40 bg-cyan-500/30" />
                heuristisch (auto)
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="size-2.5 rounded-sm border border-dashed border-zinc-600" />
                nicht zugeordnet
              </span>
              <span className="text-zinc-600">
                {filteredSystems.length}/{state.data.systems.length} Systeme
              </span>
            </div>
          </div>

          <div className="max-h-[70vh] overflow-auto rounded-lg border border-zinc-800">
            <table className="border-separate border-spacing-0 text-sm">
              <thead>
                <tr>
                  <th className="sticky left-0 top-0 z-30 border-b border-r border-zinc-800 bg-zinc-950 px-3 py-2 text-left text-xs font-medium text-zinc-400">
                    System
                  </th>
                  {state.data.concepts.map((c) => (
                    <th
                      key={c.id}
                      title={c.description ?? c.name}
                      className="sticky top-0 z-20 border-b border-zinc-800 bg-zinc-950 px-2 py-2 text-center align-bottom text-[0.7rem] font-medium text-zinc-400"
                    >
                      <span className="inline-block max-w-[6.5rem] whitespace-normal leading-tight">
                        {c.name}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredSystems.length === 0 ? (
                  <tr>
                    <td
                      colSpan={state.data.concepts.length + 1}
                      className="px-3 py-10 text-center text-sm text-zinc-500"
                    >
                      {`Keine Systeme für „${filter}“.`}
                    </td>
                  </tr>
                ) : (
                  filteredSystems.map((s) => (
                    <tr key={s.id} className="group/row">
                      <th
                        scope="row"
                        className="sticky left-0 z-10 whitespace-nowrap border-b border-r border-zinc-800 bg-zinc-950 px-3 py-1.5 text-left font-normal group-hover/row:bg-zinc-900"
                      >
                        <span className="inline-flex items-center gap-1.5">
                          <span className="font-mono text-xs text-zinc-200">
                            {s.name}
                          </span>
                          {s.provenance === "programmatic" ? (
                            <span
                              title="programmatisch"
                              className="rounded-sm border border-violet-500/30 bg-violet-500/10 px-1 text-[0.6rem] uppercase tracking-wide text-violet-300"
                            >
                              prog
                            </span>
                          ) : null}
                          {s.origin === "ui" ? (
                            <span
                              title="in der UI angelegt"
                              className="rounded-sm border border-emerald-500/30 bg-emerald-500/10 px-1 text-[0.6rem] uppercase tracking-wide text-emerald-300"
                            >
                              ui
                            </span>
                          ) : null}
                        </span>
                      </th>
                      {state.data.concepts.map((c) => {
                        const key = edgeKey(s.id, c.id);
                        const source = state.data.edges.get(key);
                        const busy = busyKey === key;
                        return (
                          <td
                            key={c.id}
                            className="border-b border-zinc-800/70 p-1 text-center"
                          >
                            <button
                              type="button"
                              onClick={() => void toggle(s.id, c.id)}
                              disabled={busy}
                              title={
                                source === "heuristic"
                                  ? "heuristisch — klicken zum Entfernen"
                                  : source === "manual"
                                    ? "manuell — klicken zum Entfernen"
                                    : "klicken zum Zuordnen"
                              }
                              className={cn(
                                "inline-flex size-6 items-center justify-center rounded-sm border transition-colors disabled:cursor-wait disabled:opacity-60",
                                source === "heuristic"
                                  ? "border-cyan-500/40 bg-cyan-500/25 hover:bg-cyan-500/40"
                                  : source === "manual"
                                    ? "border-violet-500/40 bg-violet-500/25 hover:bg-violet-500/40"
                                    : "border-dashed border-zinc-700 bg-transparent hover:border-zinc-500 hover:bg-zinc-800/50",
                              )}
                            >
                              {busy ? (
                                <Loader2 className="size-3 animate-spin text-zinc-300" />
                              ) : null}
                            </button>
                          </td>
                        );
                      })}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
