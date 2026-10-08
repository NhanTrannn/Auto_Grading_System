/**
 * "Nâng cao" switch for the barem builder.
 *
 * Most of what a teacher authors is prose — the question, what each criterion
 * checks, the accepted answers. The rest (slot ids, part labels on a one-part
 * question, sample_id, the JSON key beside every label) is plumbing the editor
 * already generates correctly, and showing it by default made the form read
 * like a schema. It stays one click away rather than gone, because validation
 * messages name those keys and someone fixing one needs to see them.
 *
 * Remembered per browser; a blocked localStorage just means it starts off.
 */
import { createContext, useContext, useState, type ReactNode } from "react";

const STORAGE_KEY = "mmlab.barem.advanced";

const AdvancedContext = createContext(false);

export function useAdvancedMode(): boolean {
  return useContext(AdvancedContext);
}

export function AdvancedModeProvider({ value, children }: { value: boolean; children: ReactNode }) {
  return <AdvancedContext.Provider value={value}>{children}</AdvancedContext.Provider>;
}

export function useAdvancedToggle(): [boolean, (next: boolean) => void] {
  const [advanced, setAdvanced] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === "1";
    } catch {
      return false;
    }
  });
  const update = (next: boolean) => {
    setAdvanced(next);
    try {
      localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
    } catch {
      // Not persisted this time; the toggle still works for the session.
    }
  };
  return [advanced, update];
}
