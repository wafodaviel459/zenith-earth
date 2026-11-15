import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

export const LANGUAGES = ["en", "fr", "es", "ar", "zh", "pt"] as const;
export type Language = (typeof LANGUAGES)[number];
type Messages = { [key: string]: string | Messages };

interface LanguageContextValue {
  language: Language;
  ready: boolean;
  error: string | null;
  setLanguage: (language: Language) => Promise<void>;
  t: (key: string, values?: Record<string, string | number>) => string;
}

const LANGUAGE_STORAGE_KEY = "zenith-earth-language";
const LanguageContext = createContext<LanguageContextValue | null>(null);

function isLanguage(value: string | null): value is Language {
  return LANGUAGES.some((language) => language === value);
}

function findMessage(messages: Messages, key: string): string | undefined {
  // Les clés séparées par des points naviguent dans l'objet JSON des traductions.
  let value: string | Messages | undefined = messages;
  for (const part of key.split(".")) {
    if (!value || typeof value === "string") return undefined;
    value = value[part];
  }
  return typeof value === "string" ? value : undefined;
}

async function loadMessages(language: Language): Promise<Messages> {
  const response = await fetch(`/locales/${language}.json`);
  if (!response.ok) throw new Error(String(response.status));
  return await response.json() as Messages;
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(() => {
    try {
      const saved = localStorage.getItem(LANGUAGE_STORAGE_KEY);
      return isLanguage(saved) ? saved : "en";
    } catch {
      return "en";
    }
  });
  const [messages, setMessages] = useState<Messages>({});
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);

  const changeLanguage = useCallback(async (nextLanguage: Language) => {
    // Un numéro de requête empêche une réponse lente de remplacer le choix le plus récent.
    const currentRequest = ++requestId.current;
    setError(null);
    setReady(false);
    try {
      const nextMessages = await loadMessages(nextLanguage);
      if (currentRequest !== requestId.current) return;
      setMessages(nextMessages);
      setLanguageState(nextLanguage);
      setReady(true);
      try {
        localStorage.setItem(LANGUAGE_STORAGE_KEY, nextLanguage);
      } catch {
        setError(
          findMessage(nextMessages, "ui.languageSaveError")
          ?? "Language changed for this session, but could not be saved on this device.",
        );
      }
    } catch (loadError) {
      if (currentRequest !== requestId.current) return;
      const status = loadError instanceof Error && /^\d{3}$/.test(loadError.message)
        ? loadError.message
        : null;
      const message = findMessage(messages, "ui.languageFileError")
        ?? "The language file could not be loaded.";
      setError(status ? `${message} (${status})` : message);
      setReady(false);
    }
  }, []);

  useEffect(() => {
    // Synchronise la langue et le sens de lecture avec les métadonnées de la page.
    void changeLanguage(language).catch(() => undefined);
  }, []);

  useEffect(() => {
    document.documentElement.lang = language;
    document.documentElement.dir = language === "ar" ? "rtl" : "ltr";
    const title = findMessage(messages, "meta.title");
    const description = findMessage(messages, "meta.description");
    if (title) document.title = title;
    if (description) document.querySelector<HTMLMetaElement>('meta[name="description"]')?.setAttribute("content", description);
  }, [language, messages]);

  const translate = useCallback((key: string, values?: Record<string, string | number>) => {
    const template = findMessage(messages, key) ?? key;
    if (!values) return template;
    return template.replace(/\{(\w+)\}/g, (match, name: string) => String(values[name] ?? match));
  }, [messages]);

  const value = useMemo<LanguageContextValue>(() => ({
    language,
    ready,
    error,
    setLanguage: changeLanguage,
    t: translate,
  }), [changeLanguage, error, language, ready, translate]);

  if (!ready) return (
    <main className="i18n-status" aria-live="polite" aria-busy={!error}>
      {error
        ? <><p>{error}</p><button type="button" onClick={() => void changeLanguage(language)}>{findMessage(messages, "ui.languageRetry") ?? "Retry language loading"}</button></>
        : <p>{findMessage(messages, "ui.languageLoading") ?? "Loading language…"}</p>}
    </main>
  );
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  const context = useContext(LanguageContext);
  if (!context) throw new Error("useLanguage must be used within LanguageProvider.");
  return context;
}

export function LanguageSelect({ className = "" }: { className?: string }) {
  const { language, setLanguage, t, error } = useLanguage();
  return (
    <label className={`language-select ${className}`} title={error || undefined}>
      <span className="sr-only">{t("language.select")}</span>
      <select value={language} aria-label={t("language.select")} onChange={(event) => {
        void setLanguage(event.target.value as Language);
      }}>
        <option value="en">{t("language.english")}</option>
        <option value="fr">{t("language.french")}</option>
        <option value="es">{t("language.spanish")}</option>
        <option value="ar">{t("language.arabic")}</option>
        <option value="zh">{t("language.chinese")}</option>
        <option value="pt">{t("language.portuguese")}</option>
      </select>
    </label>
  );
}
