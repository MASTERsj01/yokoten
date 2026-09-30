"use client";

import { useSyncExternalStore } from "react";

export const ROLES = [
  { value: "new_engineer", label: "New engineer", sees: "public + internal" },
  { value: "engineer", label: "Engineer", sees: "+ confidential" },
  { value: "quality_sme", label: "Quality SME", sees: "+ restricted, can verify answers" },
  { value: "admin", label: "Admin", sees: "everything" },
] as const;
export const SME_ROLES = ["quality_sme", "admin"];
const KEY = "yokoten-role";
const EVENT = "yokoten-role-change";

function read(): string {
  try {
    return window.localStorage.getItem(KEY) ?? "admin";
  } catch {
    return "admin";
  }
}

export function setRole(role: string) {
  try {
    window.localStorage.setItem(KEY, role);
  } catch {}
  window.dispatchEvent(new Event(EVENT));
}

/** Demo role (sent as X-Role on every API call). Server snapshot = admin. */
export function useRole(): string {
  return useSyncExternalStore(
    (cb) => {
      window.addEventListener(EVENT, cb);
      window.addEventListener("storage", cb);
      return () => {
        window.removeEventListener(EVENT, cb);
        window.removeEventListener("storage", cb);
      };
    },
    read,
    () => "admin",
  );
}
