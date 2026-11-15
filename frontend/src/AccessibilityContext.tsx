import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

// Valeurs exposées aux feuilles de style et conservées dans le navigateur.
export type Theme = "light" | "dark";
export type TextSize = "compact" | "standard" | "large" | "extraLarge";
export type DetailLevel = "student" | "expert";

export interface AccessibilitySettings {
  theme: Theme;
  colorBlind: boolean;
  textSize: TextSize;
  dyslexiaFriendly: boolean;
  reduceMotion: boolean;
  detailLevel: DetailLevel;
}

interface AccessibilityContextValue {
  settings: AccessibilitySettings;
  updateSettings: (next: Partial<AccessibilitySettings>) => void;
  resetSettings: () => void;
}

const STORAGE_KEY = "zenith-earth-accessibility";
const DEFAULT_SETTINGS: AccessibilitySettings = {
  theme: "light",
  colorBlind: false,
  textSize: "standard",
  dyslexiaFriendly: false,
  reduceMotion: false,
  detailLevel: "student",
};

const AccessibilityContext = createContext<AccessibilityContextValue | null>(null);

function getInitialSettings(): AccessibilitySettings {
  // Les anciennes valeurs ou un JSON invalide ne doivent pas empêcher l'application de démarrer.
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return DEFAULT_SETTINGS;
    const parsed = JSON.parse(stored) as Partial<AccessibilitySettings>;
    const storedTextSize = parsed.textSize as string | undefined;
    const textSize: TextSize =
      storedTextSize === "compact" || storedTextSize === "standard" ||
      storedTextSize === "large" || storedTextSize === "extraLarge"
        ? storedTextSize
        : storedTextSize === "largest" ? "extraLarge" : "standard";
    return {
      ...DEFAULT_SETTINGS,
      ...parsed,
      theme: parsed.theme === "dark" ? "dark" : "light",
      textSize,
      detailLevel: parsed.detailLevel === "expert" ? "expert" : "student",
    };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function AccessibilityProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<AccessibilitySettings>(getInitialSettings);

  useEffect(() => {
    // Les attributs HTML pilotent les variantes CSS; le stockage rend le choix durable.
    document.documentElement.dataset.theme = settings.theme;
    document.documentElement.dataset.colorblind = String(settings.colorBlind);
    document.documentElement.dataset.textSize = settings.textSize;
    document.documentElement.dataset.dyslexia = String(settings.dyslexiaFriendly);
    document.documentElement.dataset.reduceMotion = String(settings.reduceMotion);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    } catch {
      // The settings remain active for this session if storage is unavailable.
    }
  }, [settings]);

  const value = useMemo<AccessibilityContextValue>(() => ({
    settings,
    updateSettings: (next) => setSettings((current) => ({ ...current, ...next })),
    resetSettings: () => setSettings(DEFAULT_SETTINGS),
  }), [settings]);

  return <AccessibilityContext.Provider value={value}>{children}</AccessibilityContext.Provider>;
}

export function useAccessibility(): AccessibilityContextValue {
  const context = useContext(AccessibilityContext);
  if (!context) throw new Error("useAccessibility doit être utilisé dans AccessibilityProvider.");
  return context;
}
