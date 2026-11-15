# 🌍 Zénith Earth

> **English Summary (NASA Space Apps Challenge — "Be an Earth System Trend Detective!")**  
> **Zénith Earth**, built by **Team Zénith** (EMINES – UM6P, Ben Guerir, Morocco), is an interactive educational web application designed to help high-school students investigate Urban Heat Islands (UHI) and local climate trends using real NASA satellite observations. By comparing the daytime Land Surface Temperature (`MOD11A2.061` / `LST_Day_1km`) of any city against a rural reference point (~45 km north), the platform pairs a 3D interactive globe with deseasonalized annual Ordinary Least Squares (OLS) linear regression, non-parametric Mann–Kendall trend testing, and linear projections up to 2100, wrapped in a multilingual (6 languages) and WCAG/Okabe-Ito accessible interface[cite: 5].

---

**Zénith Earth**, par l’Équipe Zénith, est une application pédagogique d’enquête sur les îlots de chaleur urbains[cite: 5]. Elle compare la température de surface terrestre (LST) d’une ville à celle d’un point témoin situé environ 45 km au nord, à partir du produit MODIS `MOD11A2.061` (`LST_Day_1km`), qui fournit des composites de 8 jours à une résolution spatiale de 1 km[cite: 5]. Il s’agit de température de surface, pas de température de l’air ni d’une preuve de causalité à lui seul[cite: 5].

## Arborescence

```text
zenith-earth/
├── backend/
│   ├── demo_data/             # Quatre jeux mensuels pré-calculés, générés au démarrage
│   ├── cache/                 # Résultats JSON mis en cache après analyse
│   ├── .env.example
│   ├── .gitignore
│   ├── import_nasa_archives.py
│   ├── main.py
│   ├── pending_tasks.json     # Identifiants AppEEARS en attente
│   ├── requirements.txt
│   ├── statistics_engine.py
│   └── test_statistics_engine.py
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── AccessibilityContext.tsx
│   │   ├── LanguageContext.tsx
│   │   ├── i18n.css
│   │   ├── index.css
│   │   ├── main.tsx
│   │   └── types.ts
│   ├── public/
│   │   └── locales/           # Traductions chargées à la demande (en, fr, es, ar, zh, pt)
│   ├── .env.example
│   ├── .gitignore
│   ├── index.html
│   ├── package-lock.json
│   ├── package.json
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   ├── tsconfig*.json
│   ├── vercel.json
│   └── vite.config.ts
└── README.md
```[cite: 5]

Les fichiers de `demo_data/` sont créés automatiquement au démarrage du backend et contiennent des séries mensuelles simulées et reproductibles (2000–2025) pour les quatre villes[cite: 5]. Les valeurs sont explicitement signalées comme pédagogiques et ne doivent pas être interprétées comme des observations MODIS réelles[cite: 5].

## Lancement local

Prérequis : Python 3.11+ et Node.js 20+[cite: 5].

### API FastAPI

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```[cite: 5]

Ajoutez vos identifiants NASA Earthdata (`NASA_EARTHDATA_USER` et `NASA_EARTHDATA_PASS`) au fichier `backend/.env` pour activer AppEEARS[cite: 5]. Sans identifiants, l’API démarre directement en mode démo[cite: 5]. L’endpoint de santé est `http://localhost:8000/api/health`, la documentation Swagger `http://localhost:8000/docs`[cite: 5].

Test du moteur statistique : `python -m unittest test_statistics_engine.py` depuis le dossier `backend`[cite: 5].

### Application React

Dans un second terminal :

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```[cite: 5]

Ouvrez `http://localhost:5173`[cite: 5]. Si nécessaire, configurez `VITE_API_URL` dans `frontend/.env` pour indiquer l’URL publique de l’API[cite: 5].

### Parcours et accessibilité

Le frontend propose cinq routes : `/` (accueil), `/auth` (connexion ou accès invité), `/explore` (sélection du lieu et de la période), `/results` (résultats) et `/settings` (accessibilité et réglages)[cite: 5]. L’accès invité permet d’essayer l’application sans créer de compte ; le formulaire de connexion reste une démonstration locale[cite: 5].

Le mode clair est sélectionné par défaut[cite: 5]. Les préférences de thème, palette daltonienne, taille du texte, confort de lecture, réduction des animations et niveau de détail sont enregistrées localement dans le navigateur et s’appliquent à l’ensemble de l’interface[cite: 5]. La page `/settings` permet de les modifier ou de les réinitialiser[cite: 5].

L’interface est disponible en anglais (langue par défaut), français, espagnol, arabe, chinois et portugais[cite: 5]. Le sélecteur d’en-tête ou de réglages charge uniquement le fichier JSON choisi dans `frontend/public/locales/`, puis mémorise la préférence dans le navigateur[cite: 5]. L’arabe active automatiquement le sens de lecture RTL[cite: 5]. Pour ajouter une langue, créez un fichier JSON ayant les mêmes clés que les catalogues existants et ajoutez son code au type `Language` et à la liste du sélecteur dans `LanguageContext.tsx`[cite: 5].

## Calculs et données

- Une paire de coordonnées (`urban` et témoin `rural`) est soumise à AppEEARS avec le produit `MOD11A2.061`, la couche `LST_Day_1km` et les dates au format `MM-DD-YYYY`[cite: 5]. Les séries sont des composites de 8 jours; l’analyse statistique et le graphique annuel agrègent les observations disponibles[cite: 5].
- Les valeurs nulles, non numériques et les températures MODIS invalides (`T(K) ≤ 200`) sont filtrées avant l’analyse[cite: 5]. Conversion : `T(K) = T(raw) × 0,02`, puis `T(°C) = T(K) − 273,15`[cite: 5].
- La régression linéaire et le test de Mann–Kendall sont calculés sur les moyennes annuelles afin de limiter le biais des cycles saisonniers[cite: 5]. L’API renvoie la pente annuelle, l’ordonnée à l’origine, R², la p-value et les résultats de Mann–Kendall[cite: 5].
- L’API fournit une projection annuelle du seul modèle linéaire jusqu’en 2100, avec l’écart à la dernière moyenne annuelle observée et entre ville et témoin rural[cite: 5]. Sur `/results`, le curseur démarre à +30 ans; les observations restent en trait plein et les projections linéaires en pointillés[cite: 5]. Ces projections sont des extrapolations mathématiques, pas des prévisions certaines, et l’interface signale l’incertitude accrue au-delà de 30 ans[cite: 5].
- Les analyses NASA et les archives importées sont conservées dans `ZENITH_DATA_DIR/cache/` (par défaut `backend/cache/`)[cite: 5]. Les archives fournies couvrent Ben Guerir, Casablanca, Los Angeles, Phoenix, São Paulo, Yaoundé, Tromsø, Douala et Reykjavík pour 2015–2025[cite: 5]. Les exports de Casablanca, Tromsø, Douala et Reykjavík ne satisfont pas les critères de données NASA exploitables/couverture pour l’analyse; leurs caches sont donc explicitement identifiés comme modèles de secours, tandis que leurs identifiants de tâches AppEEARS restent enregistrés pour synchronisation[cite: 5].
- Pour importer à nouveau les exports `zenith-earth-*-request.json` et `zenith-earth-*-MOD11A2-061-results.csv`, lancez depuis `backend` : `python import_nasa_archives.py D:\donnees`[cite: 5].
- Lorsqu’une ville n’est pas en cache et que les identifiants NASA sont configurés, l’API enregistre l’identifiant AppEEARS dans `pending_tasks.json`, répond immédiatement avec `status: "queued_nasa"` et vérifie la tâche en arrière-plan toutes les 30 secondes, jusqu’à 45 minutes[cite: 5]. Quand l’extraction est terminée, son CSV est analysé et mis en cache[cite: 5]. `GET /api/nasa/sync` permet aussi de retrouver les tâches AppEEARS terminées et de récupérer leurs fichiers manquants[cite: 5].
- Le cache peut être conservé entre les redémarrages en montant un disque persistant et en définissant `ZENITH_DATA_DIR` vers son point de montage[cite: 5]. Les réponses précisent `data_source` (`nasa_appeears` ou `fallback_model`) et indiquent si elles proviennent du cache[cite: 5].

## Déploiement

### Frontend sur Vercel

1. Importez le dépôt dans Vercel et définissez **Root Directory** sur `frontend`[cite: 5].
2. Framework : Vite[cite: 5]. Commande de build : `npm run build`[cite: 5]. Répertoire de sortie : `dist`[cite: 5].
3. Configurez `VITE_API_URL` avec l’URL publique du backend Render (sans slash final), puis déployez[cite: 5].
4. `vercel.json` inclut la réécriture nécessaire au routage de l’application[cite: 5].

### Backend sur Render

1. Créez un Web Service lié au dépôt et configurez le **Root Directory** sur `backend`[cite: 5].
2. Runtime : Python[cite: 5]. Build command : `pip install -r requirements.txt`[cite: 5].
3. Start command : `uvicorn main:app --host 0.0.0.0 --port $PORT`[cite: 5].
4. Définissez `ALLOWED_ORIGINS` avec les origines frontend autorisées, séparées par des virgules, et pour les analyses en direct `NASA_EARTHDATA_USER` / `NASA_EARTHDATA_PASS`[cite: 5].
5. Pour conserver le cache entre les redémarrages, attachez un disque Render monté sur `/var/data` et définissez `ZENITH_DATA_DIR=/var/data`[cite: 5]. Sans disque persistant, les données de démo sont recréées au démarrage et le cache est éphémère[cite: 5].

Pour un essai sans déploiement, sélectionnez l’une des quatre enquêtes préchargées : Ben Guerir, Casablanca, Phoenix ou Paris[cite: 5].