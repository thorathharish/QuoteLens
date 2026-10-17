"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { getRole, setRole, type Role } from "@/lib/api/client";

export const ROLES: { value: Role; label: string }[] = [
  { value: "QUOTE_ENGINEER", label: "Quote engineer" },
  { value: "SOURCING", label: "Sourcing" },
  { value: "ENGINEERING", label: "Design engineer" },
  { value: "MANAGER", label: "Program manager" },
  { value: "VIEWER", label: "Viewer" },
];

const RoleContext = createContext<{ role: Role; change: (role: Role) => void }>({
  role: "QUOTE_ENGINEER",
  change: () => undefined,
});

export function RoleProvider({ children }: { children: React.ReactNode }) {
  const [role, setState] = useState<Role>("QUOTE_ENGINEER");
  useEffect(() => setState(getRole()), []);
  const change = (next: Role) => {
    setRole(next);
    setState(next);
  };
  return <RoleContext.Provider value={{ role, change }}>{children}</RoleContext.Provider>;
}

export const useRole = () => useContext(RoleContext);

/** Demo role switcher: decisions are attributed to this role in the audit trail. */
export function RoleSwitcher() {
  const { role, change } = useRole();
  return (
    <label className="flex items-center gap-2 text-sm text-ink-2">
      <span>Acting as</span>
      <select
        value={role}
        onChange={(e) => change(e.target.value as Role)}
        className="rounded-md border border-rule-strong bg-silk px-2 py-1 text-sm text-ink"
      >
        {ROLES.map((r) => (
          <option key={r.value} value={r.value}>
            {r.label}
          </option>
        ))}
      </select>
    </label>
  );
}
