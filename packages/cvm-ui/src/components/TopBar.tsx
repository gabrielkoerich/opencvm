import type { Component } from "solid-js";
import { A } from "@solidjs/router";

const NAV: ReadonlyArray<{ href: string; label: string }> = [
  { href: "/screeners", label: "Screeners" },
  { href: "/portfolios", label: "Portfolios" },
  { href: "/companies", label: "Companies" },
  { href: "/compare", label: "Compare" },
];

export const TopBar: Component = () => (
  <header class="flex h-10 shrink-0 items-center gap-6 border-b border-border bg-bg-elev px-4 font-mono text-xs uppercase tracking-wider text-text-dim">
    <A href="/" class="font-mono text-amber" end>
      OpenCVM
    </A>
    <nav class="flex gap-5">
      {NAV.map((item) => (
        <A
          href={item.href}
          class="hover:text-text"
          activeClass="text-text"
          inactiveClass=""
        >
          {item.label}
        </A>
      ))}
    </nav>
  </header>
);
