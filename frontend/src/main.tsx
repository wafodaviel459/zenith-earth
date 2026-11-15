import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AccessibilityProvider } from "./AccessibilityContext";
import { LanguageProvider } from "./LanguageContext";
import App from "./App";
import "./index.css";
import "./i18n.css";

// Applique le thème avant le premier rendu pour éviter un flash de couleurs incorrectes.
try {
  const savedSettings = localStorage.getItem("zenith-earth-accessibility");
  const savedTheme = savedSettings ? JSON.parse(savedSettings).theme : "light";
  document.documentElement.dataset.theme = savedTheme === "dark" ? "dark" : "light";
} catch {
  document.documentElement.dataset.theme = "light";
}

// Les fournisseurs exposent navigation, accessibilité et langue à toutes les pages.
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AccessibilityProvider>
        <LanguageProvider>
          <App />
        </LanguageProvider>
      </AccessibilityProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
