import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import type { GlobeMethods } from "react-globe.gl";
import {
  Activity,
  ArrowLeft,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  CircleHelp,
  Compass,
  Database,
  Eye,
  Globe2,
  Info,
  MapPin,
  Moon,
  Search,
  Settings,
  Sparkles,
  Sun,
  Thermometer,
  UserRound,
  X,
} from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ICity } from "country-state-city";
import { useAccessibility } from "./AccessibilityContext";
import { LanguageSelect, useLanguage } from "./LanguageContext";
import type { AnalysisResult, Location, MonthlyObservation, Point, TrendProjectionPoint } from "./types";
import nasaLogo from "../nasa-seeklogo (1).png";

// Le globe 3D est volumineux : son chargement différé accélère l'affichage initial.
const Globe = lazy(() => import("react-globe.gl"));
// La même base d'API est utilisée pour toutes les routes backend.
const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");
const DEMO_CITIES: Location[] = [
  { city_name: "Ben Guerir", country: "Maroc", lat: 32.23, lon: -7.95 },
  { city_name: "Casablanca", country: "Maroc", lat: 33.57, lon: -7.59 },
  { city_name: "Phoenix", country: "États-Unis", lat: 33.45, lon: -112.07 },
  { city_name: "Paris", country: "France", lat: 48.86, lon: 2.35 },
];
const currentYear = new Date().getFullYear() - 1;
type Suggestion = Location & { label: string };
type Toast = { id: number; text: string; tone: "info" | "success" };
type ChartMode = "annual" | "monthly";
type ResultsChartPoint = {
  date: string;
  city_c: number | null;
  rural_c: number | null;
  city_linear: number | null;
  rural_linear: number | null;
  city_linear_projection: number | null;
  rural_linear_projection: number | null;
};

// Petite aide accessible au clavier qui complète les termes statistiques.
function HelpTip({ children, label }: { children: ReactNode; label: string }) {
  const { t } = useLanguage();
  return (
    <span className="help-wrap" tabIndex={0} aria-label={`${t("ui.help")} : ${label}`}>
      <CircleHelp size={14} aria-hidden="true" />
      <span className="help-popover" role="tooltip">{children}</span>
    </span>
  );
}

function formatNumber(value: number, digits = 2): string {
  // La langue de formatage suit le catalogue actuellement chargé.
  const locale = document.documentElement.lang || "en";
  return new Intl.NumberFormat(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
}

function formatP(value: number): string {
  const locale = document.documentElement.lang || "en";
  return value < 0.001 ? `< ${new Intl.NumberFormat(locale, { minimumFractionDigits: 3, maximumFractionDigits: 3 }).format(0.001)}` : formatNumber(value, 3);
}

function makeErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error) return error.message;
  return fallback;
}

// Navigation persistante : accès aux réglages, langue, thème et profil de session.
function Header({ profile }: { profile: string }) {
  const { settings, updateSettings } = useAccessibility();
  const { t } = useLanguage();
  const location = useLocation();
  const isDark = settings.theme === "dark";
  return (
    <header className="global-nav">
      <Link className="brand" to="/" aria-label={t("header.home")}>
        <img className="brand-logo" src={nasaLogo} alt="NASA" />
        <span className="brand-copy"><strong>{t("header.brand")}</strong><small>{t("header.team")}</small></span>
      </Link>
      <nav className="global-nav-actions" aria-label={t("header.navigation")}>
        <LanguageSelect />
        <button
          className="theme-toggle"
          onClick={() => updateSettings({ theme: isDark ? "light" : "dark" })}
          aria-label={isDark ? t("header.enableLight") : t("header.enableDark")}
          title={isDark ? t("header.enableLight") : t("header.enableDark")}
        >
          {isDark ? <Sun size={16} /> : <Moon size={16} />}
          <span>{isDark ? t("header.light") : t("header.dark")}</span>
        </button>
        <Link className="settings-nav" to="/settings" state={{ from: location.pathname }}><Settings size={16} /><span>{t("header.settings")}</span></Link>
        <Link className="profile-link" to="/auth"><UserRound size={16} /><span>{profile === "Guest" || profile === "Invité" ? t("header.profileGuest") : profile}</span></Link>
      </nav>
    </header>
  );
}

// Lien de retour commun aux pages secondaires.
function BackLink({ to, children }: { to: string; children: ReactNode }) {
  return <Link className="page-back-link" to={to}><ArrowLeft size={14} />{children}</Link>;
}

// Présentation de l'application et explication du parcours en trois étapes.
function HomePage() {
  const { t } = useLanguage();
  return (
    <main className="home-page">
      <section className="home-hero">
        <div className="hero-copy">
          <span className="hero-eyebrow"><span className="live-dot" /> {t("home.eyebrow")}</span>
          <h1>{t("home.headline1")}<br /><span>{t("home.headline2")}</span></h1>
          <p>{t("home.description")}</p>
          <Link className="hero-cta" to="/auth">{t("home.start")} <ArrowRight size={17} /></Link>
          <span className="hero-note"><Database size={14} /> {t("home.data")}</span>
        </div>
        <div className="hero-art" aria-label={t("home.illustration")}>
          <div className="orbit orbit-one" /><div className="orbit orbit-two" />
          <div className="earth-art"><span className="earth-glow" /><Globe2 size={132} strokeWidth={0.75} /></div>
          <span className="orbit-label label-modis"><Activity size={13} /> {t("home.modis")}</span>
          <span className="orbit-label label-temp"><Thermometer size={13} /> {t("home.surfaceTemp")}</span>
          <span className="orbit-ping ping-one" /><span className="orbit-ping ping-two" />
        </div>
      </section>
      <section className="home-process">
        <div className="process-heading"><span className="overline"><Compass size={14} /> {t("home.threeSteps")}</span><h2>{t("home.stepsTitle")}</h2></div>
        <div className="process-grid">
          <article className="process-card"><span className="process-number">01</span><span className="process-icon"><MapPin size={20} /></span><h3>{t("home.step1Title")}</h3><p>{t("home.step1Description")}</p></article>
          <article className="process-card"><span className="process-number">02</span><span className="process-icon"><Database size={20} /></span><h3>{t("home.step2Title")}</h3><p>{t("home.step2Description")}</p></article>
          <article className="process-card"><span className="process-number">03</span><span className="process-icon"><Activity size={20} /></span><h3>{t("home.step3Title")}</h3><p>{t("home.step3Description")}</p></article>
        </div>
        <div className="home-disclaimer"><Info size={15} /> {t("home.disclaimer")}</div>
      </section>
      <footer className="page-footer"><span>{t("home.byTeam")}</span><span>{t("home.tagline")}</span></footer>
    </main>
  );
}

// Formulaire de prototype : la session est locale, sans authentification serveur.
function AuthPage({ onGuest, onToast, onSignIn }: { onGuest: () => void; onToast: (message: string) => void; onSignIn: (email: string) => void }) {
  const { t } = useLanguage();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    // L'authentification est une démonstration locale, sans création de compte serveur.
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const email = String(formData.get("email") || "").trim();
    onSignIn(email);
    onToast(t("auth.demoSession"));
  };
  return (
    <main className="auth-page">
      <section className="auth-card">
        <BackLink to="/">{t("common.backHome")}</BackLink>
        <div className="auth-emblem"><img src="/Gemini_Generated_Image_3ndztw3ndztw3ndz.jpg" alt="" aria-hidden="true" /></div>
        <span className="overline">{t("auth.eyebrow")}</span>
        <h1>{mode === "signin" ? t("auth.welcome") : t("auth.join")}</h1>
        <p>{t("auth.description")}</p>
        <div className="auth-tabs" role="tablist">
          <button role="tab" aria-selected={mode === "signin"} className={mode === "signin" ? "active" : ""} onClick={() => setMode("signin")}>{t("auth.signInTab")}</button>
          <button role="tab" aria-selected={mode === "signup"} className={mode === "signup" ? "active" : ""} onClick={() => setMode("signup")}>{t("auth.signUpTab")}</button>
        </div>
        <form className="auth-form" onSubmit={handleSubmit}>
          {mode === "signup" && <label>{t("auth.firstName")}<input name="name" autoComplete="given-name" placeholder={t("auth.firstNamePlaceholder")} required /></label>}
          <label>{t("auth.email")}<input name="email" type="email" autoComplete="email" placeholder={t("auth.emailPlaceholder")} required /></label>
          <label>{t("auth.password")}<input name="password" type="password" autoComplete={mode === "signin" ? "current-password" : "new-password"} placeholder={t("auth.passwordPlaceholder")} minLength={8} required /></label>
          <button className="auth-submit" type="submit">{mode === "signin" ? t("auth.signIn") : t("auth.signUp")} <ArrowRight size={16} /></button>
        </form>
        <div className="auth-separator"><span>{t("common.or")}</span></div>
        <button className="guest-button" onClick={onGuest}><Compass size={17} /> {t("auth.continueGuest")}</button>
        <small className="auth-prototype">{t("auth.prototype")}</small>
      </section>
    </main>
  );
}

// Les préférences sont partagées par le contexte puis appliquées aux attributs CSS du document.
function SettingsPage() {
  const { settings, updateSettings, resetSettings } = useAccessibility();
  const { t } = useLanguage();
  const location = useLocation();
  const routeState = location.state as { from?: unknown } | null;
  // N'accepte qu'une route locale sûre comme destination de retour.
  const backTo = typeof routeState?.from === "string" && routeState.from.startsWith("/") && routeState.from !== "/settings"
    ? routeState.from
    : "/";
  return (
    <main className="settings-page">
      <BackLink to={backTo}>{t("common.backPrevious")}</BackLink>
      <header className="settings-heading">
        <span className="overline"><Settings size={14} /> {t("settings.eyebrow")}</span>
        <h1>{t("settings.title")}</h1>
        <p>{t("settings.description")}</p>
      </header>
      <div className="settings-grid">
        <section className="settings-card">
          <div className="settings-card-head"><span className="settings-icon"><Eye size={18} /></span><div><h2>{t("settings.displayTitle")}</h2><p>{t("settings.displayDescription")}</p></div></div>
          <div className="setting-row"><div><b>{t("settings.appearance")}</b><small>{t("settings.appearanceDescription")}</small></div>
            <div className="segmented-control">
              <button className={settings.theme === "light" ? "selected" : ""} onClick={() => updateSettings({ theme: "light" })}><Sun size={15} /> {t("settings.lightDefault")} <small>{t("settings.default")}</small></button>
              <button className={settings.theme === "dark" ? "selected" : ""} onClick={() => updateSettings({ theme: "dark" })}><Moon size={15} /> {t("settings.darkSpace")} <small>{t("settings.space")}</small></button>
            </div>
          </div>
          <div className="setting-row"><div><b>{t("settings.textSize")}</b><small>{t("settings.textSizeDescription")}</small></div>
            <div className="segmented-control text-size-options">
              {([
                { id: "compact", label: t("settings.compact"), scale: "85 %" },
                { id: "standard", label: t("settings.standard"), scale: "100 %" },
                { id: "large", label: t("settings.large"), scale: "115 %" },
                { id: "extraLarge", label: t("settings.extraLarge"), scale: "130 %" },
              ] as const).map((option) => (
                <button key={option.id} className={settings.textSize === option.id ? "selected" : ""} onClick={() => updateSettings({ textSize: option.id })}><span>{option.label}</span><small>{option.scale}</small></button>
              ))}
            </div>
          </div>
          <div className="setting-row"><div><b>{t("settings.readingComfort")}</b><small>{t("settings.readingComfortDescription")}</small></div><Toggle checked={settings.dyslexiaFriendly} label={t("settings.enableReadingComfort")} onChange={(value) => updateSettings({ dyslexiaFriendly: value })} /></div>
          <div className="setting-row"><div><b>{t("settings.reduceAnimations")}</b><small>{t("settings.reduceAnimationsDescription")}</small></div><Toggle checked={settings.reduceMotion} label={t("settings.enableReduceAnimations")} onChange={(value) => updateSettings({ reduceMotion: value })} /></div>
        </section>
        <section className="settings-card">
          <div className="settings-card-head"><span className="settings-icon"><Activity size={18} /></span><div><h2>{t("settings.dataExploration")}</h2><p>{t("settings.dataDescription")}</p></div></div>
          <div className="setting-row"><div><b>{t("settings.colorBlind")}</b><small>{t("settings.colorBlindDescription")}</small></div><Toggle checked={settings.colorBlind} label={t("settings.enableColorBlind")} onChange={(value) => updateSettings({ colorBlind: value })} /></div>
          <div className="palette-preview" data-colorblind={settings.colorBlind}>
            <span><i className="palette-city" /> {t("settings.citySolid")}</span><span><i className="palette-rural" /> {t("settings.ruralDashed")}</span>
          </div>
          <div className="setting-row"><div><b>{t("language.label")}</b><small>{t("settings.languageDescription")}</small></div><LanguageSelect /></div>
          <div className="setting-row detail-row"><div><b>{t("settings.detailLevel")}</b><small>{t("settings.detailDescription")}</small></div>
            <div className="segmented-control detail-options">
              <button className={settings.detailLevel === "student" ? "selected" : ""} onClick={() => updateSettings({ detailLevel: "student" })}><span>{t("settings.studentMode")}</span><small>{t("settings.studentDetail")}</small></button>
              <button className={settings.detailLevel === "expert" ? "selected" : ""} onClick={() => updateSettings({ detailLevel: "expert" })}><span>{t("settings.expertMode")}</span><small>{t("settings.expertDetail")}</small></button>
            </div>
          </div>
          <aside className="settings-note"><Info size={15} /><span>{t("settings.savedInfo")}</span></aside>
        </section>
      </div>
      <div className="settings-bottom"><span>{t("settings.resetIntro")}</span><button className="reset-button" onClick={resetSettings}>{t("settings.reset")}</button></div>
    </main>
  );
}

// Interrupteur réutilisable avec un libellé accessible pour chaque réglage booléen.
function Toggle({ checked, label, onChange }: { checked: boolean; label: string; onChange: (value: boolean) => void }) {
  return <button role="switch" aria-checked={checked} aria-label={label} className={`switch ${checked ? "on" : ""}`} onClick={() => onChange(!checked)}><span /></button>;
}

// Contrat des valeurs et actions transmises depuis le composant racine à l'explorateur.
interface ExplorePageProps {
  location: Location;
  onLocationChange: (location: Location) => void;
  startYear: number;
  endYear: number;
  onStartYearChange: (year: number) => void;
  onEndYearChange: (year: number) => void;
  loading: boolean;
  loadingStep: number;
  onAnalyze: (location: Location) => void;
  onToast: (message: string, tone?: Toast["tone"]) => void;
}

// Recherche de lieu, sélection des années, globe interactif et lancement de l'analyse.
function ExplorePage(props: ExplorePageProps) {
  const { settings } = useAccessibility();
  const { language, t } = useLanguage();
  const {
    location, onLocationChange, startYear, endYear, onStartYearChange,
    onEndYearChange, loading, loadingStep, onAnalyze, onToast,
  } = props;
  const [search, setSearch] = useState("");
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [searchBusy, setSearchBusy] = useState(false);
  const [selectedCountry, setSelectedCountry] = useState("");
  const [selectedState, setSelectedState] = useState("");
  const [showCascade, setShowCascade] = useState(false);
  const [geoCatalog, setGeoCatalog] = useState<typeof import("country-state-city") | null>(null);
  const [globeReady, setGlobeReady] = useState(false);
  const [globeSize, setGlobeSize] = useState({ width: 0, height: 0 });
  const globeRef = useRef<GlobeMethods | undefined>(undefined);
  const searchAbort = useRef<AbortController | null>(null);
  const selectedSearch = useRef(false);
  const globeContainer = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    // ResizeObserver fournit au globe sa taille réelle, y compris après un redimensionnement.
    const element = globeContainer.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        setGlobeSize({
          width: Math.floor(entry.contentRect.width),
          height: Math.floor(entry.contentRect.height),
        });
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    // La recherche est temporisée et annulable pour éviter des appels obsolètes au géocodeur.
    if (selectedSearch.current) {
      selectedSearch.current = false;
      setSuggestions([]);
      setSearchBusy(false);
      return;
    }
    const query = search.trim();
    if (query.length < 2) {
      setSuggestions([]);
      return;
    }
    searchAbort.current?.abort();
    const controller = new AbortController();
    searchAbort.current = controller;
    const timer = window.setTimeout(async () => {
      setSearchBusy(true);
      try {
        const url = new URL("https://geocoding-api.open-meteo.com/v1/search");
        url.search = new URLSearchParams({ name: query, count: "6", language, format: "json" }).toString();
        const response = await fetch(url, { signal: controller.signal });
        if (!response.ok) throw new Error(t("explore.geocodingError"));
        const data = await response.json() as { results?: { name: string; country?: string; latitude: number; longitude: number; admin1?: string }[] };
        setSuggestions((data.results || []).map((item) => ({
          city_name: item.name, country: item.country || item.admin1 || t("explore.selectedCountry"),
          lat: item.latitude, lon: item.longitude,
          label: [item.name, item.admin1, item.country].filter(Boolean).join(", "),
        })));
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setSuggestions([]);
          onToast(makeErrorMessage(error, t("errors.unexpected")));
        }
      } finally {
        if (!controller.signal.aborted) setSearchBusy(false);
      }
    }, 300);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [language, onToast, search, t]);

  useEffect(() => {
    // Recentrer le globe sur le lieu choisi tout en respectant la préférence de mouvement réduit.
    if (globeReady) {
      globeRef.current?.pointOfView({ lat: location.lat, lng: location.lon, altitude: 1.8 }, settings.reduceMotion ? 0 : 1100);
      const controls = globeRef.current?.controls();
      if (controls) {
        controls.autoRotate = !settings.reduceMotion;
        controls.autoRotateSpeed = 0.25;
        controls.enableDamping = !settings.reduceMotion;
        controls.update();
      }
    }
  }, [globeReady, location, settings.reduceMotion]);

  useEffect(() => {
    // Le catalogue hors ligne est chargé seulement si l'utilisateur ouvre les listes en cascade.
    if (showCascade && !geoCatalog) {
      import("country-state-city")
        .then(setGeoCatalog)
        .catch((error: unknown) => onToast(t("explore.directoryError", { error: makeErrorMessage(error, t("errors.unexpected")) })));
    }
  }, [geoCatalog, onToast, showCascade, t]);

  // Le point rural témoin est placé environ 45 km au nord, sans dépasser le pôle.
  const ruralMarker = useMemo<Point>(() => ({ lat: Math.min(location.lat + 0.4, 90), lon: location.lon }), [location]);
  const colorBlind = settings.colorBlind;
  const globePoints = useMemo(() => [
    { ...location, label: `${location.city_name} · ${t("common.city").toLowerCase()}`, color: colorBlind ? "#E69F00" : "#ff9c54", size: 0.8 },
    { ...ruralMarker, label: t("explore.ruralMarker"), color: colorBlind ? "#0072B2" : "#65dfc2", size: 0.55 },
  ], [colorBlind, location, ruralMarker, t]);
  const countryList = geoCatalog?.Country.getAllCountries() || [];
  const regions = selectedCountry ? geoCatalog?.State.getStatesOfCountry(selectedCountry) || [] : [];
  const cities = selectedCountry && selectedState ? geoCatalog?.City.getCitiesOfState(selectedCountry, selectedState) || [] : [];

  const selectSuggestion = (suggestion: Suggestion) => {
    // Annule la requête de recherche en cours avant de figer le lieu sélectionné.
    const target = { city_name: suggestion.city_name, country: suggestion.country, lat: suggestion.lat, lon: suggestion.lon };
    searchAbort.current?.abort();
    selectedSearch.current = true;
    setSearch(suggestion.label);
    setSuggestions([]);
    setSearchBusy(false);
    onLocationChange(target);
  };

  const selectCascadeCity = (city: ICity | undefined) => {
    if (!city?.latitude || !city.longitude) return;
    const country = countryList.find((item) => item.isoCode === selectedCountry);
    const target = {     city_name: city.name, country: country?.name || t("explore.selectedCountry"), lat: Number(city.latitude), lon: Number(city.longitude) };
    if (Number.isFinite(target.lat) && Number.isFinite(target.lon)) onLocationChange(target);
  };

  const onGlobeClick = (coordinates: { lat: number; lng: number }) => {
    onLocationChange({
      city_name: t("explore.locationPoint", { lat: coordinates.lat.toFixed(2), lon: coordinates.lng.toFixed(2) }),
      country: t("explore.selectedCoordinates"), lat: coordinates.lat, lon: coordinates.lng,
    });
  };

  return (
    <main className="explore-page">
      <aside className="explore-panel">
        <BackLink to="/auth">{t("explore.back")}</BackLink>
        <div className="explore-title"><span className="step-number">01</span><div><h1>{t("explore.chooseArea")}</h1><p>{t("explore.chooseAreaDescription")}</p></div></div>
        <div className="field-block">
          <label htmlFor="place-search">{t("explore.searchCity")}</label>
          <div className="search-field">
            <Search size={16} />
            <input id="place-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("explore.searchPlaceholder")} autoComplete="off" aria-autocomplete="list" aria-expanded={suggestions.length > 0} />
            {searchBusy && <span className="search-spinner" aria-label={t("explore.searchLoading")} />}
            {suggestions.length > 0 && <div className="suggestions" role="listbox">{suggestions.map((item) => <button role="option" aria-selected="false" key={`${item.label}-${item.lat}`} onClick={() => selectSuggestion(item)}><MapPin size={15} /><span><b>{item.city_name}</b><small>{item.label}</small></span></button>)}</div>}
          </div>
          <small className="field-hint">{t("explore.searchHint")}</small>
        </div>
        <button className={`cascade-toggle ${showCascade ? "open" : ""}`} onClick={() => setShowCascade((value) => !value)} aria-expanded={showCascade}>
          <span><Globe2 size={16} /> {t("explore.offlineLocations")}</span><ChevronDown size={16} />
        </button>
        {showCascade && <div className="cascade-fields">
          <label>{t("explore.country")}<select value={selectedCountry} onChange={(event) => { setSelectedCountry(event.target.value); setSelectedState(""); }}><option value="">{geoCatalog ? t("explore.chooseCountry") : t("explore.loadingDirectory")}</option>{countryList.map((country) => <option key={country.isoCode} value={country.isoCode}>{country.name}</option>)}</select></label>
          <label>{t("explore.region")}<select value={selectedState} disabled={!selectedCountry} onChange={(event) => setSelectedState(event.target.value)}><option value="">{t("explore.chooseRegion")}</option>{regions.map((region) => <option key={region.isoCode} value={region.isoCode}>{region.name}</option>)}</select></label>
          <label>{t("explore.city")}<select disabled={!selectedState} defaultValue="" onChange={(event) => selectCascadeCity(cities[Number(event.target.value)])}><option value="">{t("explore.chooseCity")}</option>{cities.map((city, index) => <option key={`${city.name}-${index}`} value={index}>{city.name}</option>)}</select></label>
        </div>}
        <div className="panel-divider" />
        <div className="explore-title period-title"><span className="step-number">02</span><div><h2>{t("explore.choosePeriod")}</h2><p>{t("explore.periodDescription")}</p></div></div>
        <div className="year-fields">
          <label>{t("explore.from")}<select value={startYear} onChange={(event) => onStartYearChange(Number(event.target.value))}>{Array.from({ length: currentYear - 2001 }, (_, index) => currentYear - index - 2).map((year) => <option key={year} value={year}>{year}</option>)}</select></label>
          <span className="year-dash">—</span>
          <label>{t("explore.to")}<select value={endYear} onChange={(event) => onEndYearChange(Number(event.target.value))}>{Array.from({ length: currentYear - 1999 }, (_, index) => currentYear - index).filter((year) => year >= startYear + 2).map((year) => <option key={year} value={year}>{year}</option>)}</select></label>
        </div>
        <div className="period-note"><Activity size={13} /> {t("explore.monthsToAnalyze", { count: Math.max(0, endYear - startYear + 1) * 12 })}</div>
        <button className="analyze-button" onClick={() => onAnalyze(location)} disabled={loading || endYear - startYear < 2}>
          {loading ? <><span className="button-spinner" /> {t("explore.analyzing")}</> : <><Sparkles size={16} /> {t("explore.launch")} <ArrowUpRight size={16} /></>}
        </button>
        {loading && <div className="progress-card" aria-live="polite">
          <div className="progress-head"><span>{t("explore.progressTitle")}</span><span>{Math.min(loadingStep + 1, 3)}/3</span></div>
          <div className="progress-segments">{[0, 1, 2].map((step) => <span key={step} className={step <= loadingStep ? "complete" : ""} />)}</div>
          <div className="progress-labels">{[t("explore.nasaConnection"), t("explore.modisExtraction"), t("explore.statistics")].map((label, index) => <span key={label} className={index === loadingStep ? "active" : ""}>{label}</span>)}</div>
          <p className="progress-message">{t("ui.progressMessage")}</p>
        </div>}
        <div className="explore-tip"><Info size={14} /><span>{t("explore.ruralInfo")}</span></div>
      </aside>
      <section className="globe-card explore-globe" aria-label={t("explore.globeLabel")}>
        <div className="globe-topline"><span className="globe-tag"><span className="live-dot" /> {t("explore.globeLabel")}</span><span className="coordinates">{Math.abs(location.lat).toFixed(2)}° {location.lat < 0 ? "S" : "N"} · {Math.abs(location.lon).toFixed(2)}° {location.lon < 0 ? "O" : "E"}</span></div>
        <div className="globe-stage" ref={globeContainer}>
          <Suspense fallback={<div className="globe-loading">{t("explore.globeLoading")}</div>}>
            {globeSize.width > 0 && globeSize.height > 0 ? <Globe ref={globeRef} width={globeSize.width} height={globeSize.height}
              backgroundColor="rgba(0,0,0,0)" globeImageUrl="https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg"
              backgroundImageUrl="https://unpkg.com/three-globe/example/img/night-sky.png" showAtmosphere
              atmosphereColor="#8fb9ff" atmosphereAltitude={0.16} pointsData={globePoints}
              pointLat="lat" pointLng="lon" pointColor="color" pointAltitude={0.035}
              pointRadius="size" pointLabel="label" onGlobeClick={onGlobeClick}
              onGlobeReady={() => setGlobeReady(true)}
            /> : <div className="globe-loading">{t("explore.globeLoading")}</div>}
          </Suspense>
          <div className="globe-instruction"><span className="click-ring" /> {t("explore.globeHint")}</div>
        </div>
        <div className="map-legend"><span><i className={`legend-city ${colorBlind ? "colorblind" : ""}`} /> {t("explore.cityMarker")}</span><span><i className={`legend-rural ${colorBlind ? "colorblind" : ""}`} /> {t("explore.ruralMarker")}</span><span className="north-note">{t("explore.north")}</span></div>
        <div className="globe-footer"><span><Thermometer size={14} /> {t("explore.lst")}</span><span>{t("explore.monthlyResolution")}</span></div>
      </section>
      <div className="explore-quick-cities" aria-label={t("explore.quickSurveys")}>{DEMO_CITIES.map((city) => <button key={city.city_name} className={location.city_name === city.city_name ? "selected" : ""} onClick={() => onLocationChange(city)}>{city.city_name}</button>)}</div>
    </main>
  );
}

// Résultat d'analyse courant et action pour relancer un parcours.
interface ResultsPageProps {
  result: AnalysisResult | null;
  onNewAnalysis: () => void;
}

function annualObservations(series: MonthlyObservation[]): MonthlyObservation[] {
  // Agrège les composites de 8 jours en moyennes annuelles pour le mode de graphique annuel.
  const groups = new Map<string, MonthlyObservation[]>();
  for (const point of series) {
    const year = point.date.slice(0, 4);
    groups.set(year, [...(groups.get(year) || []), point]);
  }
  const mean = (values: (number | null)[]) => {
    const valid = values.filter((value): value is number => value !== null && Number.isFinite(value));
    return valid.length ? valid.reduce((sum, value) => sum + value, 0) / valid.length : null;
  };
  return [...groups.entries()].map(([year, points]) => ({
    date: `${year}-01-01`,
    city_c: mean(points.map((point) => point.city_c)) || 0,
    rural_c: mean(points.map((point) => point.rural_c)) || 0,
    city_linear: mean(points.map((point) => point.city_linear)) || 0,
    rural_linear: mean(points.map((point) => point.rural_linear)) || 0,
  }));
}

function ResultsPage({ result, onNewAnalysis }: ResultsPageProps) {
  const { settings } = useAccessibility();
  const { t, language } = useLanguage();
  const [chartMode, setChartMode] = useState<ChartMode>("annual");
  const [selectedProjectionYear, setSelectedProjectionYear] = useState<number | null>(null);
  const [chartHeight, setChartHeight] = useState(260);
  const chartArea = useRef<HTMLDivElement | null>(null);
  const cityStats = result?.statistics.city;
  const minProjectionYear = Math.min(2100, (result?.period.end_year ?? currentYear) + 10);
  const projectionYear = Math.min(
    2100,
    Math.max(minProjectionYear, selectedProjectionYear ?? (result?.period.end_year ?? currentYear) + 30),
  );
  const yearsAhead = result ? projectionYear - result.period.end_year : 0;
  const projectionPoints = result?.projection?.points ?? [];
  const selectedProjection = projectionPoints.find((point) => point.year === projectionYear);
  const significant = cityStats ? cityStats.p_value < 0.05 : false;
  const colorBlind = settings.colorBlind;
  const cityColor = colorBlind ? "#E69F00" : settings.theme === "dark" ? "#ff9c54" : "#d97706";
  const ruralColor = colorBlind ? "#0072B2" : settings.theme === "dark" ? "#78a8ff" : "#2563eb";
  const annualData = useMemo(() => {
    if (!result) return [];
    const observed = annualObservations(result.series);
    const lastObserved = observed[observed.length - 1];
    if (!lastObserved) return [];
    // La courbe projetée prolonge la dernière observation jusqu'à l'horizon sélectionné.
    const selectedPoints = projectionPoints.filter((point) => point.year <= projectionYear);
    return [
      ...observed.map((point, index) => ({
        ...point,
        city_linear_projection: index === observed.length - 1 ? point.city_linear : null,
        rural_linear_projection: index === observed.length - 1 ? point.rural_linear : null,
      })),
      ...selectedPoints.map((point) => ({
        date: `${point.year}-01-01`,
        city_c: null,
        rural_c: null,
        city_linear: null,
        rural_linear: null,
        city_linear_projection: point.city_linear_c,
        rural_linear_projection: point.rural_linear_c,
      })),
    ] satisfies ResultsChartPoint[];
  }, [projectionPoints, projectionYear, result]);
  const chartData = useMemo<ResultsChartPoint[]>(() => {
    if (!result) return [];
    if (chartMode === "annual") return annualData;
    return result.series.map((point) => ({
      ...point,
      city_linear_projection: null,
      rural_linear_projection: null,
    }));
  }, [annualData, chartMode, result]);
  const observedAnnualData = annualData.filter((point) => point.city_c !== null);
  const actualEndDate = observedAnnualData[observedAnnualData.length - 1]?.date;
  const projectionEndDate = `${projectionYear}-01-01`;

  useEffect(() => {
    // Ajuste le graphique à la hauteur disponible dans la carte de résultats.
    const element = chartArea.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      if (entries[0]) setChartHeight(Math.max(170, Math.floor(entries[0].contentRect.height)));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  if (!result || !cityStats) {
    return <main className="results-page"><div className="no-results"><span className="process-icon"><Activity size={23} /></span><h1>{t("results.noneTitle")}</h1><p>{t("results.noneDescription")}</p><button className="hero-cta" onClick={onNewAnalysis}>{t("results.start")} <ArrowRight size={16} /></button></div></main>;
  }

  const isPositive = cityStats.slope_c_per_year >= 0;
  const statsExpert = [
    { label: t("results.ruralSlope"), value: `${formatNumber(result.statistics.rural.slope_c_per_year, 3)} ${t("results.perYear")}` },
    { label: t("results.mannKendallP"), value: formatP(cityStats.mann_kendall.p_value) },
    { label: t("results.kendallTau"), value: formatNumber(cityStats.mann_kendall.tau, 3) },
  ];

  return (
    <main className="results-page">
      <div className="results-toolbar">
        <button className="back-button" onClick={onNewAnalysis}>{t("results.new")}</button>
        <div className="results-location"><span className="results-pin"><MapPin size={15} /></span><b>{result.city}</b><span>{result.country} · {result.period.start_year}–{result.period.end_year}</span></div>
        <span className={`results-source ${result.mode}`}>{result.mode === "live" ? t("results.liveSource") : t("results.demoSource")}</span>
      </div>
      {result.status === "queued_nasa" && <p className="nasa-sync-note" role="status">{result.notice}</p>}
      <div className="results-kpis">
        <article className="metric-card trend-metric"><div className="metric-label">{t("results.cityTrend")} <HelpTip label={t("results.annualRate")}>{t("results.annualRateHelp")}</HelpTip></div><div className="metric-value">{isPositive ? "+" : ""}{formatNumber(cityStats.slope_c_per_year, 3)}<small>{t("results.perYear")}</small></div><div className="metric-foot">{isPositive ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />} {t("results.annualTrend")}</div></article>
        <article className="metric-card"><div className="metric-label">{t("results.urbanRuralGap")} <HelpTip label={t("results.urbanRuralGap")}>{t("results.heatIslandHelp")}</HelpTip></div><div className="metric-value">{formatNumber(result.statistics.mean_urban_rural_difference_c)}<small>°C</small></div><div className="metric-foot">{t("results.periodAverage")}</div></article>
        <article className="metric-card"><div className="metric-label">{t("results.significance")} <HelpTip label={t("results.significance")}>{t("results.pValueHelp")}</HelpTip></div><div className={`metric-value ${significant ? "value-green" : "value-amber"}`}>{formatP(cityStats.p_value)}</div><div className="metric-foot">{significant ? <><Check size={13} /> {t("results.signalDetected")}</> : t("results.signalUncertain")}</div></article>
        <article className="metric-card"><div className="metric-label">{t("results.fitQuality")} <HelpTip label="R²">{t("results.rSquaredHelp")}</HelpTip></div><div className="metric-value">{formatNumber(cityStats.r_squared)}</div><div className="metric-foot">{t("results.annualR2")}</div></article>
      </div>
      {settings.detailLevel === "expert" && <section className="expert-strip" aria-label={t("results.extraIndicators")}>{statsExpert.map((stat) => <div key={stat.label}><small>{stat.label}</small><b>{stat.value}</b></div>)}</section>}
      <section className="results-chart-card">
        <div className="chart-heading">
          <div><h1>{t("results.surfaceTemperature", { city: result.city })}</h1><p>{chartMode === "annual" ? t("results.annualSubtitle") : t("results.monthlySubtitle")}</p></div>
          <div className="chart-unit">{t("results.degrees")}</div>
        </div>
        <div className="chart-controls">
          <div className="chart-mode-toggle" role="group" aria-label={t("results.visualizationMode")}>
            <button className={chartMode === "annual" ? "active" : ""} onClick={() => setChartMode("annual")}>{t("results.annualMode")}</button>
            <button className={chartMode === "monthly" ? "active" : ""} onClick={() => setChartMode("monthly")}>{t("results.seasonalMode")}</button>
          </div>
          <div className="curve-toggles" role="group" aria-label={t("results.chartCurves")}>
            <span className="curve-indicator"><i className="curve-swatch linear-city" style={{ background: cityColor }} />{t("results.cityRegression")}</span>
            <span className="curve-indicator"><i className="curve-swatch linear-rural" style={{ background: ruralColor }} />{t("results.ruralRegression")}</span>
          </div>
        </div>
        <div className="results-chart-area" ref={chartArea}>
          <ResponsiveContainer width="100%" height={chartHeight}>
            <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 3, left: 0 }}>
              {chartMode === "annual" && actualEndDate && <ReferenceArea x1={actualEndDate} x2={projectionEndDate} fill={settings.theme === "dark" ? "#f5a623" : "#f59e0b"} fillOpacity={settings.theme === "dark" ? 0.08 : 0.09} />}
              <CartesianGrid stroke={settings.theme === "dark" ? "#253447" : "#e2e8f0"} strokeDasharray="3 5" vertical={false} />
              <XAxis dataKey="date" tickFormatter={(value: string) => chartMode === "annual" ? value.slice(0, 4) : value.slice(5, 7)} minTickGap={chartMode === "annual" ? 22 : 36} tick={{ fill: settings.theme === "dark" ? "#8290a4" : "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis domain={["auto", "auto"]} tick={{ fill: settings.theme === "dark" ? "#8290a4" : "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} width={48} tickFormatter={(value: number) => `${formatNumber(value, 0)}°`} />
              <Tooltip content={({ active, payload, label }) => active && payload?.length ? <div className="chart-tooltip"><strong>{chartMode === "annual" ? String(label).slice(0, 4) : new Date(String(label)).toLocaleDateString(language, { month: "long", year: "numeric", timeZone: "UTC" })}</strong>{payload.map((item) => <span key={String(item.dataKey)} style={{ color: item.color }}><i />{item.name} : {typeof item.value === "number" ? `${formatNumber(item.value)} °C` : t("common.notAvailable")}</span>)}</div> : null} />
              {chartMode === "annual" && actualEndDate && <ReferenceLine x={actualEndDate} stroke={settings.theme === "dark" ? "#fbbf24" : "#b45309"} strokeDasharray="4 4" label={{ value: t("results.today"), position: "insideTopRight", fill: settings.theme === "dark" ? "#fcd34d" : "#92400e", fontSize: 9 }} />}
              <Line type="monotone" dataKey="city_c" name={t("results.observedCity")} stroke={cityColor} strokeWidth={2.2} dot={false} isAnimationActive={!settings.reduceMotion} />
              <Line type="monotone" dataKey="rural_c" name={t("results.observedCountryside")} stroke={ruralColor} strokeWidth={2.2} strokeDasharray={colorBlind ? "7 4" : undefined} dot={false} isAnimationActive={!settings.reduceMotion} />
              <Line type="linear" dataKey="city_linear" name={t("results.linearCity")} stroke={cityColor} strokeWidth={1.8} dot={false} isAnimationActive={false} />
              <Line type="linear" dataKey="rural_linear" name={t("results.linearRural")} stroke={ruralColor} strokeWidth={1.8} dot={false} isAnimationActive={false} />
              {chartMode === "annual" && <>
                <Line type="linear" dataKey="city_linear_projection" name={t("results.linearCityProjection")} stroke={cityColor} strokeWidth={2} strokeDasharray="2 4" dot={false} isAnimationActive={false} />
                <Line type="linear" dataKey="rural_linear_projection" name={t("results.linearRuralProjection")} stroke={ruralColor} strokeWidth={2} strokeDasharray="2 4" dot={false} isAnimationActive={false} />
              </>}
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="chart-legend-row"><span><i className="observed-city" /> {t("common.city")}</span><span><i className="observed-rural" /> {t("common.rural")}</span><span><i className="annual-legend" /> {t("results.average")}</span><small>{t("results.sourceLabel")}: {result.source}</small></div>
      </section>
      <section className={`projection-card ${yearsAhead > 30 ? "long-horizon" : ""}`} aria-labelledby="projection-title">
        <div className="projection-heading">
          <div className="projection-title"><b id="projection-title">{t("results.projectionTitle")}</b><span>{t("results.projectionBase", { year: result.projection?.baseline_year ?? result.period.end_year })}</span></div>
          <div className="projection-metrics">
            <div><small>{t("results.urbanTemperature")}</small><b>{selectedProjection ? `${formatNumber(selectedProjection.city_linear_c)} °C` : t("common.notAvailable")}</b></div>
            <div><small>{t("results.deltaToday")}</small><b>{selectedProjection ? `${selectedProjection.city_linear_delta_c > 0 ? "+" : ""}${formatNumber(selectedProjection.city_linear_delta_c)} °C` : t("common.notAvailable")}</b></div>
            <div><small>{t("results.heatIslandGap")}</small><b>{selectedProjection ? `${selectedProjection.urban_rural_linear_difference_c > 0 ? "+" : ""}${formatNumber(selectedProjection.urban_rural_linear_difference_c)} °C` : t("common.notAvailable")}</b></div>
          </div>
        </div>
        <div className="projection-control">
          <label htmlFor="projection-horizon">{t("results.horizon")} <strong>{projectionYear}</strong> <span>{t("results.plusYears", { years: yearsAhead })}</span></label>
          <input id="projection-horizon" type="range" min={minProjectionYear} max="2100" step="1" value={projectionYear} disabled={!projectionPoints.length} onChange={(event) => { setSelectedProjectionYear(Number(event.target.value)); setChartMode("annual"); }} aria-valuetext={`${projectionYear}, dans ${yearsAhead} ans`} />
          <span className="projection-range-label">{t("results.plus10")}</span><span className="projection-range-label">2100</span>
        </div>
        <p className="projection-caveat"><Info size={13} /><span>{!projectionPoints.length
          ? t("results.projectionUnavailable")
          : yearsAhead > 30
          ? t("results.longProjectionWarning")
          : t("results.projectionWarning")}</span></p>
        {chartMode === "monthly" && <p className="projection-chart-hint">{t("results.chooseAnnual")}</p>}
      </section>
      <section className="results-takeaway"><span className="takeaway-icon"><Sparkles size={16} /></span><div><b>{t("results.takeaway")}</b><p>{significant
        ? t(isPositive ? "summary.positive" : "summary.negative", { city: result.city, p: formatP(cityStats.p_value), slope: formatNumber(Math.abs(cityStats.slope_c_per_year), 3), gap: formatNumber(result.statistics.mean_urban_rural_difference_c) })
        : t("results.notSignificantSummary", { city: result.city, p: formatP(cityStats.p_value) })}
        <small>{t("results.scienceNote")}</small></p></div></section>
    </main>
  );
}

// État global du parcours : sélection, chargement, navigation et notifications.
function App() {
  const navigate = useNavigate();
  const { settings } = useAccessibility();
  const { t } = useLanguage();
  const [location, setLocation] = useState<Location>(DEMO_CITIES[0]);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [startYear, setStartYear] = useState(2015);
  const [endYear, setEndYear] = useState(2025);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [profile, setProfile] = useState(() => sessionStorage.getItem("zenith-earth-profile") || "Guest");
  const toastCounter = useRef(0);

  const pushToast = useCallback((text: string, tone: Toast["tone"] = "info") => {
    const id = ++toastCounter.current;
    setToasts((current) => [...current, { id, text, tone }]);
    window.setTimeout(() => setToasts((current) => current.filter((toast) => toast.id !== id)), 4000);
  }, []);

  const runAnalysis = useCallback(async (target: Location) => {
    // Annuler un appel qui dépasse la limite client évite de laisser l'interface en attente;
    // le backend répond normalement tout de suite et termine l'extraction NASA en arrière-plan.
    setLocation(target);
    setLoading(true);
    setLoadingStep(0);
    const progressTimer = window.setInterval(() => setLoadingStep((step) => Math.min(step + 1, 2)), 8500);
    const requestController = new AbortController();
    const requestTimeout = window.setTimeout(() => requestController.abort(), 310_000);
    try {
      const response = await fetch(`${API_URL}/api/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ city_name: target.city_name, country: target.country, lat: target.lat, lon: target.lon, start_year: startYear, end_year: endYear }),
        signal: requestController.signal,
      });
      const payload = await response.json() as AnalysisResult | { detail?: string };
      if (!response.ok) throw new Error("detail" in payload ? payload.detail || t("errors.analysisFailed") : t("errors.analysisFailed"));
      const analysis = payload as AnalysisResult;
      setResult(analysis);
      if (analysis.cache_hit) pushToast(t("toast.cached"), "success");
      if (analysis.mode === "demo" && analysis.notice && analysis.status !== "queued_nasa") pushToast(analysis.notice);
      navigate("/results");
    } catch (error) {
      pushToast(makeErrorMessage(error, t("errors.unexpected")));
    } finally {
      window.clearInterval(progressTimer);
      window.clearTimeout(requestTimeout);
      setLoading(false);
    }
  }, [endYear, navigate, pushToast, startYear, t]);

  const chartVisible = settings.detailLevel === "expert";
  const handleSignIn = (email: string) => {
    const label = email ? email.split("@")[0] : "Guest";
    setProfile(label);
    sessionStorage.setItem("zenith-earth-profile", label);
    navigate("/explore");
  };
  const startNewAnalysis = () => navigate("/explore");

  return (
    <>
      <Header profile={profile} />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/auth" element={<AuthPage onGuest={() => { setProfile("Guest"); navigate("/explore"); }} onToast={pushToast} onSignIn={handleSignIn} />} />
        <Route path="/explore" element={<ExplorePage location={location} onLocationChange={setLocation} startYear={startYear} endYear={endYear} onStartYearChange={setStartYear} onEndYearChange={setEndYear} loading={loading} loadingStep={loadingStep} onAnalyze={runAnalysis} onToast={pushToast} />} />
        <Route path="/results" element={<ResultsPage result={result} onNewAnalysis={startNewAnalysis} />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      {chartVisible && result && <span className="sr-only" aria-live="polite">{t("a11y.expertNotice")}</span>}
      <div className="toast-stack" aria-live="polite" aria-atomic="false">{toasts.map((toast) => <div key={toast.id} className={`toast ${toast.tone}`}><span className="toast-mark">{toast.tone === "success" ? <Check size={15} /> : <Sparkles size={15} />}</span>{toast.text}<button aria-label={t("toast.close")} onClick={() => setToasts((items) => items.filter((item) => item.id !== toast.id))}><X size={14} /></button></div>)}</div>
    </>
  );
}

export default App;
