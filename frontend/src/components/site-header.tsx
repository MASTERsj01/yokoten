"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { MoonIcon, SunIcon, UserRoundIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import { ROLES, setRole, useRole } from "@/lib/role";
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
    <span
      className="text-muted-foreground hidden items-center gap-1.5 text-xs md:flex"
      title={label}
      aria-live="polite"
    >
      <span
        className={cn(
          "size-2 rounded-full",
          state === "up" ? "bg-emerald-500" : state === "down" ? "animate-pulse bg-amber-500" : "bg-muted-foreground",
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

function RoleSwitcher() {
  const role = useRole();
  return (
    <Select
      value={role}
      onValueChange={(r) => {
        setRole(r);
        window.location.reload(); // every page re-fetches with the new X-Role
      }}
    >
      <SelectTrigger
        size="sm"
        className="hidden w-auto gap-1.5 sm:flex"
        aria-label="Demo role (access control)"
        title="Demo role - retrieval only returns documents this role may read"
      >
        <UserRoundIcon className="size-3.5" />
        <SelectValue>{ROLES.find((r) => r.value === role)?.label ?? role}</SelectValue>
      </SelectTrigger>
      <SelectContent align="end">
        {ROLES.map((r) => (
          <SelectItem key={r.value} value={r.value}>
            {r.label} <span className="text-muted-foreground text-xs">({r.sees})</span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function SiteHeader() {
  const pathname = usePathname();
  return (
    <header className="bg-background/90 sticky top-0 z-40 border-b backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <span
            className="bg-primary text-primary-foreground grid size-7 place-items-center rounded-md text-sm"
            aria-hidden
          >
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
                "text-muted-foreground hover:bg-accent hover:text-foreground rounded-md px-2.5 py-1.5 transition-colors",
                pathname.startsWith(n.href) && "bg-accent text-foreground",
              )}
            >
              {n.label}
            </Link>
          ))}
        </nav>
        <BackendStatus />
        <RoleSwitcher />
        <ThemeToggle />
      </div>
    </header>
  );
}
