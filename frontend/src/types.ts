// Contrats communs entre le sélecteur de lieu, l'API et les graphiques.
export interface Location {
  city_name: string;
  country: string;
  lat: number;
  lon: number;
}

// Coordonnées affichées sur le globe ou renvoyées par l'API.
export interface Point {
  lat: number;
  lon: number;
}

// Observation (composite MODIS) et valeurs ajustées utilisées dans les graphiques.
export interface MonthlyObservation {
  date: string;
  city_c: number;
  rural_c: number;
  city_linear: number;
  rural_linear: number;
}

// Résumé du test non paramétrique de tendance de Mann–Kendall.
export interface MannKendall {
  trend: string;
  p_value: number;
  tau: number;
  slope_per_month: number;
}

// Statistiques de tendance calculées séparément pour la ville et le point rural.
export interface SiteStatistics {
  slope_c_per_year: number;
  intercept_c: number;
  r_squared: number;
  p_value: number;
  mann_kendall: MannKendall;
}

// Valeurs annuelles extrapolées pour une année future donnée.
export interface TrendProjectionPoint {
  year: number;
  city_linear_c: number;
  rural_linear_c: number;
  city_linear_delta_c: number;
  urban_rural_linear_difference_c: number;
}

// Base observée et ensemble de points de projection jusqu'à l'horizon configuré.
export interface TrendProjection {
  baseline_year: number;
  baseline_city_c: number;
  baseline_rural_c: number;
  points: TrendProjectionPoint[];
}

export interface AnalysisResult {
  // queued_nasa signifie que le backend renvoie un modèle provisoire pendant l'extraction NASA.
  status?: "queued_nasa";
  city: string;
  country: string;
  coordinates: Point;
  rural_coordinates: Point;
  period: { start_year: number; end_year: number };
  source: string;
  mode: "live" | "demo";
  notice: string | null;
  cache_hit: boolean;
  series: MonthlyObservation[];
  projection: TrendProjection;
  statistics: {
    city: SiteStatistics;
    rural: SiteStatistics;
    mean_urban_rural_difference_c: number;
  };
}
