import { useAuthStore } from "../store/useAuthStore";

export function HomePage() {
  const { user } = useAuthStore();

  return (
    <div>
      <h1 className="text-2xl font-semibold text-slate-900 mb-4">
        Bienvenido, {user?.nombre}
      </h1>
      <p className="text-slate-600">
        Dashboard en construcción. Las funcionalidades estarán disponibles en próximas versiones.
      </p>
    </div>
  );
}
