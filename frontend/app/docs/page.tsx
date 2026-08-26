"use client";

import { useEffect, useMemo, useState } from "react";

import { DOC_SECTIONS, type DocBlock } from "@/lib/docs-content";
import { cn } from "@/lib/utils";

/**
 * The user guide.
 *
 * Renders `lib/docs-content.ts` generically: the table of contents, the
 * anchors and the scroll-spy all come from the same array, so adding a section
 * there needs no change here. Search filters sections and subsections by their
 * text, which is the cheapest thing that actually helps in a guide this long —
 * anything cleverer would need an index that could go stale.
 */

const NOTE_STYLES: Record<string, { box: string; label: string; title: string }> = {
  info: {
    box: "border-sky-500/30 bg-sky-500/5",
    label: "text-sky-300",
    title: "Hinweis",
  },
  warn: {
    box: "border-amber-500/30 bg-amber-500/5",
    label: "text-amber-300",
    title: "Achtung",
  },
  good: {
    box: "border-emerald-500/30 bg-emerald-500/5",
    label: "text-emerald-300",
    title: "Gut zu wissen",
  },
};

function Block({ block }: { block: DocBlock }) {
  switch (block.kind) {
    case "p":
      return (
        <p className="text-sm leading-relaxed text-zinc-300">{block.text}</p>
      );

    case "list":
      return (
        <ul className="space-y-1.5">
          {block.items.map((item, i) => (
            <li
              key={i}
              className="flex gap-2.5 text-sm leading-relaxed text-zinc-300"
            >
              <span aria-hidden className="mt-2 size-1 shrink-0 rounded-full bg-zinc-600" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      );

    case "steps":
      return (
        <ol className="space-y-2.5">
          {block.items.map((item, i) => (
            <li key={i} className="flex gap-3 text-sm leading-relaxed text-zinc-300">
              <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border border-zinc-700 bg-zinc-900 font-mono text-[11px] tabular-nums text-zinc-400">
                {i + 1}
              </span>
              <span>{item}</span>
            </li>
          ))}
        </ol>
      );

    case "table":
      return (
        <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 bg-zinc-900/50">
                {block.head.map((h) => (
                  <th
                    key={h}
                    className="px-3 py-2 text-left text-xs font-medium tracking-wide text-zinc-400 uppercase"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, i) => (
                <tr key={i} className="border-b border-zinc-800/60 last:border-0">
                  {row.map((cell, j) => (
                    <td
                      key={j}
                      className={cn(
                        "px-3 py-2 align-top leading-relaxed",
                        j === 0 ? "font-medium text-zinc-200" : "text-zinc-400",
                      )}
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );

    case "code":
      return (
        <pre className="overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-900/60 p-3 font-mono text-xs leading-relaxed text-zinc-300">
          {block.text}
        </pre>
      );

    case "note": {
      const style = NOTE_STYLES[block.tone] ?? NOTE_STYLES.info;
      return (
        <div className={cn("rounded-lg border px-3.5 py-3", style.box)}>
          <div className={cn("text-xs font-semibold tracking-wide uppercase", style.label)}>
            {block.title}
          </div>
          <p className="mt-1.5 text-sm leading-relaxed text-zinc-300">{block.text}</p>
        </div>
      );
    }
  }
}

function matches(haystack: string, needle: string) {
  return haystack.toLowerCase().includes(needle.toLowerCase());
}

function blockText(block: DocBlock): string {
  switch (block.kind) {
    case "p":
    case "code":
      return block.text;
    case "list":
    case "steps":
      return block.items.join(" ");
    case "table":
      return [...block.head, ...block.rows.flat()].join(" ");
    case "note":
      return `${block.title} ${block.text}`;
  }
}

export default function DocsPage() {
  const [query, setQuery] = useState("");
  const [activeId, setActiveId] = useState<string>(DOC_SECTIONS[0]?.id ?? "");

  const sections = useMemo(() => {
    const q = query.trim();
    if (!q) return DOC_SECTIONS;
    return DOC_SECTIONS.map((section) => {
      // A section whose own title matches keeps all of its subsections;
      // otherwise only the subsections that match survive.
      if (matches(`${section.title} ${section.lede}`, q)) return section;
      const subsections = section.subsections.filter((sub) =>
        matches(`${sub.title} ${sub.blocks.map(blockText).join(" ")}`, q),
      );
      return subsections.length ? { ...section, subsections } : null;
    }).filter((s): s is (typeof DOC_SECTIONS)[number] => s !== null);
  }, [query]);

  // Scroll-spy: highlight the section currently nearest the top of the view.
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActiveId(visible[0].target.id);
      },
      { rootMargin: "-80px 0px -70% 0px" },
    );
    for (const section of sections) {
      const el = document.getElementById(section.id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [sections]);

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-8">
      <div className="mb-6">
        <h1 className="text-xl font-semibold tracking-tight text-zinc-100">
          Anleitung
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-zinc-400">
          Wie die Plattform benutzt wird — von den Einstellungen über den
          Strategie-Designer bis zum Live-Journal. Beschreibt den Stand, der
          gerade läuft, einschließlich dessen, was er nicht tut.
        </p>
      </div>

      <div className="flex flex-col gap-8 lg:flex-row lg:items-start">
        {/* Table of contents */}
        <nav
          aria-label="Inhaltsverzeichnis"
          className="lg:sticky lg:top-20 lg:w-64 lg:shrink-0"
        >
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Anleitung durchsuchen…"
            aria-label="Anleitung durchsuchen"
            className="mb-3 w-full rounded-md border border-zinc-800 bg-zinc-900/60 px-3 py-1.5 text-sm text-zinc-200 placeholder:text-zinc-600 focus:border-zinc-600 focus:outline-none"
          />
          {sections.length === 0 ? (
            <p className="px-2 text-xs text-zinc-500">
              Nichts gefunden für „{query}“.
            </p>
          ) : (
            <ul className="space-y-0.5">
              {sections.map((section) => (
                <li key={section.id}>
                  <a
                    href={`#${section.id}`}
                    className={cn(
                      "block rounded-md px-2.5 py-1.5 text-sm transition-colors",
                      activeId === section.id
                        ? "bg-zinc-800 font-medium text-zinc-100"
                        : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200",
                    )}
                  >
                    {section.title}
                  </a>
                  {activeId === section.id && section.subsections.length > 1 ? (
                    <ul className="mt-0.5 mb-1 ml-3 space-y-0.5 border-l border-zinc-800 pl-2">
                      {section.subsections.map((sub) => (
                        <li key={sub.id}>
                          <a
                            href={`#${sub.id}`}
                            className="block rounded px-2 py-1 text-xs text-zinc-500 transition-colors hover:text-zinc-300"
                          >
                            {sub.title}
                          </a>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </nav>

        {/* Content */}
        <div className="min-w-0 flex-1 space-y-12">
          {sections.map((section) => (
            <section key={section.id} id={section.id} className="scroll-mt-20">
              <header className="border-b border-zinc-800 pb-3">
                <h2 className="text-lg font-semibold tracking-tight text-zinc-100">
                  {section.title}
                </h2>
                <p className="mt-1 text-sm text-zinc-500">{section.lede}</p>
              </header>

              <div className="mt-6 space-y-8">
                {section.subsections.map((sub) => (
                  <div key={sub.id} id={sub.id} className="scroll-mt-20">
                    <h3 className="mb-3 text-xs font-semibold tracking-wide text-zinc-400 uppercase">
                      {sub.title}
                    </h3>
                    <div className="space-y-3">
                      {sub.blocks.map((block, i) => (
                        <Block key={i} block={block} />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </main>
  );
}
