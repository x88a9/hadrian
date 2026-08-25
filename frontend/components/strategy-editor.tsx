"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import { Textarea } from "@/components/ui/textarea";

export interface StrategyEditorProps {
  value: string;
  onChange: (value: string) => void;
  language: "python" | "json";
  height?: number | string;
  readOnly?: boolean;
}

type MonacoModule = typeof import("@monaco-editor/react");

// Monaco selbst wird von @monaco-editor/loader per <script>-Tag von einem CDN
// nachgeladen (kein lokales Bundle-Gewicht) -- das erst passiert, wenn
// loader.init() aufgerufen wird. Faellt das (kein Netz, CDN blockiert), bleibt
// die interne <Editor>-Komponente stumm im "loading"-Zustand haengen: ihr
// eigener init()-Aufruf faengt den Fehler nur mit console.error ab und
// rendert für immer weiter den Ladeindikator. Deshalb ruft dieser Wrapper
// loader.init() selbst auf, wertet Erfolg/Fehlschlag/Timeout aus und
// degradiert erst dann kontrolliert auf ein <textarea>.
let monacoModulePromise: Promise<MonacoModule> | null = null;

function loadMonacoModule(): Promise<MonacoModule> {
  if (!monacoModulePromise) {
    monacoModulePromise = import("@monaco-editor/react");
  }
  return monacoModulePromise;
}

const INIT_TIMEOUT_MS = 8000;

type LoadStatus = "loading" | "ready" | "failed";

function PlainTextarea({
  value,
  onChange,
  height,
  readOnly,
}: {
  value: string;
  onChange: (value: string) => void;
  height?: number | string;
  readOnly?: boolean;
}) {
  return (
    <Textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      readOnly={readOnly}
      spellCheck={false}
      className="font-mono text-xs leading-relaxed"
      style={{ height: height ?? 400, resize: "vertical" }}
    />
  );
}

// Monaco-Wrapper. Degradiert kontrolliert auf ein <textarea>, wenn Monaco
// nicht laedt (Netzwerk/CDN-Problem) oder das Laden zu lange dauert.
export function StrategyEditor({
  value,
  onChange,
  language,
  height = 480,
  readOnly = false,
}: StrategyEditorProps) {
  const [status, setStatus] = useState<LoadStatus>("loading");
  const [mod, setMod] = useState<MonacoModule | null>(null);

  useEffect(() => {
    let cancelled = false;
    let initPromise: (Promise<unknown> & { cancel?: () => void }) | null = null;

    loadMonacoModule()
      .then((loaded) => {
        if (cancelled) return;
        initPromise = loaded.loader.init();
        const timeout = new Promise<never>((_, reject) => {
          setTimeout(
            () => reject(new Error("Monaco-Ladezeit überschritten")),
            INIT_TIMEOUT_MS,
          );
        });
        return Promise.race([initPromise, timeout]).then(() => {
          if (cancelled) return;
          setMod(loaded);
          setStatus("ready");
        });
      })
      .catch(() => {
        if (!cancelled) setStatus("failed");
      });

    return () => {
      cancelled = true;
      initPromise?.cancel?.();
    };
  }, []);

  if (status === "failed") {
    return (
      <PlainTextarea
        value={value}
        onChange={onChange}
        height={height}
        readOnly={readOnly}
      />
    );
  }

  if (status === "loading" || !mod) {
    return (
      <div
        className="flex items-center justify-center gap-2 rounded-md border border-zinc-800 bg-zinc-900/60 text-sm text-zinc-500"
        style={{ height }}
      >
        <Loader2 className="size-4 animate-spin" />
        Editor wird geladen…
      </div>
    );
  }

  const MonacoEditor = mod.default;

  return (
    <div className="overflow-hidden rounded-md border border-zinc-800">
      <MonacoEditor
        height={height}
        language={language}
        theme="vs-dark"
        value={value}
        onChange={(v) => onChange(v ?? "")}
        options={{
          minimap: { enabled: false },
          fontSize: 13,
          readOnly,
          scrollBeyondLastLine: false,
          automaticLayout: true,
          tabSize: 2,
        }}
      />
    </div>
  );
}
