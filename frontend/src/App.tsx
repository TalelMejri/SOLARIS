import { useEffect, useState } from "react";
import {
  BrowserRouter as Router,
  Routes,
  Route,
  Navigate,
} from "react-router-dom";
import { Provider } from "react-redux";
import LoadingScreen from "./components/common/LoadingComponents";
import { ThemeProvider } from "./contexts/ThemeProvider";
import { LanguageProvider } from "./i18n";
import HeroSection from "./pages/home/Home";
import Dashboard from "./pages/dashboard/Dashboard";
import ProtectedRoute from "./guard/protectedRoutes";
import PublicRoute from "./guard/publicRoutes";
import { store } from "./AuthStore/store";
import GridImpactAnalysis from "./pages/dashboard/GridImpactAnalysis";
import PVInstallationManagement from "./pages/dashboard/PVInstallationManagement";

function AppShell() {
  const [isLoading, setIsLoading] = useState(true);
  const [showLoader, setShowLoader] = useState(true);

  useEffect(() => {
    const hide = setTimeout(() => setIsLoading(false), 4000);
    const unmount = setTimeout(() => setShowLoader(false), 4600);
    return () => {
      clearTimeout(hide);
      clearTimeout(unmount);
    };
  }, []);

  return (
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem>
      {showLoader && (
        <div
          className={`fixed inset-0 z-100 transition-opacity duration-500 ${isLoading ? "opacity-100" : "pointer-events-none opacity-0"
            }`}
        >
          <LoadingScreen />
        </div>
      )}

      <LanguageProvider>
        <Routes>
          {/* Public — hero page */}
          <Route element={<PublicRoute />}>
            <Route path="/" element={<HeroSection />} />
          </Route>

          {/* Protected — dashboard */}
          <Route element={<ProtectedRoute />}>
            <Route path="/dashboard" element={<Dashboard />} />
          </Route>
          <Route element={<ProtectedRoute />}>
            <Route path="/dashboard/grid-impact" element={<GridImpactAnalysis />} />
          </Route>
          <Route element={<ProtectedRoute />}>
            <Route path="/dashboard/installations" element={<PVInstallationManagement />} />
          </Route>

          {/* Anything else → back to hero */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </LanguageProvider>
    </ThemeProvider>
  );
}

function App() {
  return (
    <Provider store={store}>
      <Router>
        <AppShell />
      </Router>
    </Provider>
  );
}

export default App;