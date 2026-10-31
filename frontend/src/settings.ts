import { useCallback, useState } from "react";

export interface Settings {
  /** URL de base de l'API ("" = même origine). */
  apiBase: string;
  /** Clé envoyée dans l'en-tête X-API-Key sur les écritures. */
  apiKey: string;
  /** Mode démo : données fictives intégrées. */
  demo: boolean;
}

const STORAGE_KEY = "edgebet.settings.v1";

export const DEFAULT_SETTINGS: Settings = { apiBase: "", apiKey: "", demo: false };

export function normalizeSettings(s: Settings): Settings {
  return {
    apiBase: s.apiBase.trim().replace(/\/+$/, ""),
    apiKey: s.apiKey.trim(),
    demo: Boolean(s.demo),
  };
}

export function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    const p: unknown = JSON.parse(raw);
    if (!p || typeof p !== "object") return DEFAULT_SETTINGS;
    const o = p as Record<string, unknown>;
    return normalizeSettings({
      apiBase: typeof o.apiBase === "string" ? o.apiBase : "",
      apiKey: typeof o.apiKey === "string" ? o.apiKey : "",
      demo: typeof o.demo === "boolean" ? o.demo : false,
    });
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function saveSettings(s: Settings): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    /* stockage indisponible (navigation privée, quota…) : on reste en mémoire */
  }
}

export function useSettings(): [Settings, (next: Settings) => void] {
  const [settings, setSettings] = useState<Settings>(loadSettings);
  const update = useCallback((next: Settings) => {
    const n = normalizeSettings(next);
    setSettings(n);
    saveSettings(n);
  }, []);
  return [settings, update];
}
