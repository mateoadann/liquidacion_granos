import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ProtectedRoute } from "./components/layout";
import { LoginPage, HomePage } from "./pages";
import ClientsPage from "./ClientsPage";

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {/* Ruta pública */}
          <Route path="/login" element={<LoginPage />} />

          {/* Rutas protegidas */}
          <Route element={<ProtectedRoute />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/clientes" element={<ClientsPage />} />
            {/* Placeholders para rutas futuras */}
            <Route path="/coes" element={<div className="text-slate-600">COEs - Próximamente</div>} />
            <Route path="/exportar" element={<div className="text-slate-600">Exportar - Próximamente</div>} />
          </Route>

          {/* Rutas admin */}
          <Route element={<ProtectedRoute requireAdmin />}>
            <Route path="/configuracion" element={<div className="text-slate-600">Configuración - Próximamente</div>} />
            <Route path="/configuracion/usuarios" element={<div className="text-slate-600">Usuarios - Próximamente</div>} />
          </Route>

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
