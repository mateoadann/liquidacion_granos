import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Layout } from "./components/layout/Layout";
import { ProtectedRoute } from "./components/layout";
import { LoginPage, HomePage } from "./pages";
import { ClientsListPage } from "./pages/ClientsListPage";
import { ClientDetailPage } from "./pages/ClientDetailPage";
import { ClientEditPage } from "./pages/ClientEditPage";
import { ClientCertificatesPage } from "./pages/ClientCertificatesPage";
import { CoesListPage } from "./pages/CoesListPage";
import { CoeDetailPage } from "./pages/CoeDetailPage";
import { ExportPage } from "./pages/ExportPage";
import { ConfigPage } from "./pages/ConfigPage";
import { UsersListPage } from "./pages/UsersListPage";

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
            <Route element={<Layout><HomePage /></Layout>} path="/" />
            <Route path="/clientes" element={<Layout><ClientsListPage /></Layout>} />
            <Route path="/clientes/nuevo" element={<Layout><ClientEditPage /></Layout>} />
            <Route path="/clientes/:id" element={<Layout><ClientDetailPage /></Layout>} />
            <Route path="/clientes/:id/editar" element={<Layout><ClientEditPage /></Layout>} />
            <Route path="/clientes/:id/certificados" element={<Layout><ClientCertificatesPage /></Layout>} />
            <Route path="/coes" element={<Layout><CoesListPage /></Layout>} />
            <Route path="/coes/:id" element={<Layout><CoeDetailPage /></Layout>} />
            <Route path="/exportar" element={<Layout><ExportPage /></Layout>} />
          </Route>

          {/* Rutas admin */}
          <Route element={<ProtectedRoute requireAdmin />}>
            <Route path="/configuracion" element={<Layout><ConfigPage /></Layout>} />
            <Route path="/configuracion/usuarios" element={<Layout><UsersListPage /></Layout>} />
          </Route>

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
