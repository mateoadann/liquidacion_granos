import { useNavigate } from "react-router-dom";
import { PageHeader } from "../components/layout";
import { Card, Button } from "../components/ui";

export function ConfigPage() {
  const navigate = useNavigate();

  return (
    <div>
      <PageHeader
        title="Configuración"
        subtitle="Administración del sistema"
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-2xl">
        <Card className="p-6">
          <h3 className="text-lg font-medium text-slate-900 mb-2">
            Gestión de Usuarios
          </h3>
          <p className="text-sm text-slate-500 mb-4">
            Crear, editar y administrar usuarios del sistema
          </p>
          <Button onClick={() => navigate("/configuracion/usuarios")}>
            Administrar usuarios
          </Button>
        </Card>
      </div>
    </div>
  );
}
