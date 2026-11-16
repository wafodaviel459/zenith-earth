import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import Home from './pages/Home';
import Explore from './pages/Explore';
import Results from './pages/Results';

function RequireHomeFirst({ children }) {
  const location = useLocation();
  const hasVisitedHome = sessionStorage.getItem('zenith_visited_home');

  // Si l'utilisateur est sur la page d'accueil, on marque la session comme initialisée
  if (location.pathname === '/') {
    sessionStorage.setItem('zenith_visited_home', 'true');
    return children;
  }

  // S'il accède directement à /explore ou /results sans être passé par /, on le renvoie sur /
  if (!hasVisitedHome) {
    return <Navigate to="/" replace />;
  }

  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <RequireHomeFirst>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/explore" element={<Explore />} />
          <Route path="/results" element={<Results />} />
          {/* Toute autre URL inconnue renvoie aussi vers Home */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </RequireHomeFirst>
    </BrowserRouter>
  );
}