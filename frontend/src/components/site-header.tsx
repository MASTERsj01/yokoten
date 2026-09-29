"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { MoonIcon, SunIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/chat", label: "Chat" },
  { href: "/search", label: "Search" },
  { href: "/library", label: "Library" },
  { href: "/onboarding", label: "Onboarding" },
  { href: "/eval", label: "Evaluation" },
  { href: "/settings", label: "Settings" },
];

function BackendStatus() {
  const [state, setState] = useState<"checking" | "up" | "down">("checking");
  useEffect(() => {
    let alive = true;
    const check = () =>
      api("/api/health")
        .then(() => alive && setState("up"))
        .catch(() => alive && setState("down"));
    check();
    const t = setInterval(check, 15000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);
  const label = { checking: "Connecting…", up: "Backend online", down: "Backend waking up / offline" }[state];
  return (
    <span className="hidden items-center gap-1.5 text-xs text-muted-foreground md:flex" title={label} aria-live="polite">
      <span
        className={cn(
          "size-2 rounded-full",
          state === "up" ? "bg-emerald-500" : state === "down" ? "bg-amber-500 animate-pulse" : "bg-muted-foreground",
        )}
      />
      {label}
    </span>
  );
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label="Toggle dark mode"
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
    >
      <SunIcon className="size-4 dark:hidden" />
      <MoonIcon className="hidden size-4 dark:block" />
    </Button>
  );
}

export function SiteHeader() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-40 border-b bg-background/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <span className="grid size-7 place-items-center rounded-md bg-primary text-sm text-primary-foreground" aria-hidden>
            横
          </span>
          Yokoten
        </Link>
        <nav className="flex flex-1 items-center gap-1 overflow-x-auto text-sm" aria-label="Main">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className={cn(
                "rounded-md px-2.5 py-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
                pathname.startsWith(n.href) && "bg-accent text-foreground",
              )}
            >
              {n.label}
            </Link>
          ))}
        </nav>
        <BackendStatus />
        <ThemeToggle />
      </div>
    </header>
  );
}
