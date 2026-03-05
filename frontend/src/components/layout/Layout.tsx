import { type ReactNode } from "react";
import { NavLink } from "react-router-dom";

interface LayoutProps {
  children: ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
      isActive
        ? "bg-green-50 text-green-700"
        : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
    }`;

  return (
    <div className="min-h-screen bg-slate-50">
      <nav className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex h-16 items-center justify-between">
            <div className="flex items-center space-x-8">
              <span className="text-xl font-bold text-green-600">Liquidación Primaria de Granos</span>
              <div className="flex space-x-1">
                <NavLink to="/" className={linkClass} end>
                  Inicio
                </NavLink>
                <NavLink to="/clientes" className={linkClass}>
                  Clientes
                </NavLink>
                <NavLink to="/coes" className={linkClass}>
                  COEs
                </NavLink>
                <NavLink to="/exportar" className={linkClass}>
                  Exportar
                </NavLink>
                <NavLink to="/configuracion" className={linkClass}>
                  Config
                </NavLink>
              </div>
            </div>
          </div>
        </div>
      </nav>
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>
    </div>
  );
}
