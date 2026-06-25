import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "../components/layout";
import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmModal,
  Select,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableRow,
} from "../components/ui";
import { formatDateTime } from "../dateUtils";
import { useGestionesQuery, useMarcarGestionMutation } from "../hooks/useGestiones";
import type { Gestion, GestionEstado, GestionTipo } from "../api/gestiones";

const ESTADO_META: Record<
  GestionEstado,
  { label: string; variant: "warning" | "info" | "success" | "error" }
> = {
  pendiente: { label: "Pendiente", variant: "warning" },
  realizada: { label: "Realizada", variant: "info" },
  verificada: { label: "Verificada", variant: "success" },
  verificacion_fallida: { label: "Verificación fallida", variant: "error" },
};

const TIPO_LABEL: Record<GestionTipo, string> = {
  alta_cliente: "Alta cliente",
  alta_proveedor: "Alta proveedor",
  mapeo_grano: "Mapeo grano",
  alta_cuenta: "Alta cuenta",
};

function EstadoBadge({ estado }: { estado: GestionEstado }) {
  const meta = ESTADO_META[estado];
  return (
    <Badge variant={meta.variant} className="whitespace-nowrap">
      {meta.label}
    </Badge>
  );
}

// Cada COE (14 díg.) linkea a la lista de COEs filtrada por ese número.
// No usamos /coes/<coe> porque esa ruta resuelve por id interno, no por número de COE.
function CoesCell({ coes }: { coes: string[] }) {
  if (coes.length === 0) {
    return <span className="text-gray-400">—</span>;
  }
  return (
    <div className="flex flex-col gap-0.5">
      {coes.map((coe) => (
        <Link
          key={coe}
          to={`/coes?search=${coe}`}
          className="font-mono text-sm text-emerald-700 hover:underline"
        >
          {coe}
        </Link>
      ))}
    </div>
  );
}

export function GestionesListPage() {
  const [estado, setEstado] = useState<GestionEstado | "">("");
  const [cuitEmpresa, setCuitEmpresa] = useState<string>("");
  const [confirmTarget, setConfirmTarget] = useState<Gestion | null>(null);

  // No filtramos server-side por empresa: traemos todo y agrupamos/filtramos en
  // cliente, así el selector de empresas se deriva del propio dataset.
  const gestionesQuery = useGestionesQuery(
    estado ? { estado } : undefined,
  );
  const marcarMutation = useMarcarGestionMutation();

  const todas = gestionesQuery.data?.gestiones ?? [];

  const empresas = useMemo(() => {
    const map = new Map<string, string>();
    for (const g of todas) {
      if (!map.has(g.cuit_empresa)) {
        map.set(g.cuit_empresa, g.razon_social || g.cuit_empresa);
      }
    }
    return Array.from(map.entries())
      .map(([cuit, razon]) => ({ cuit, razon }))
      .sort((a, b) => a.razon.localeCompare(b.razon));
  }, [todas]);

  const visibles = useMemo(
    () => (cuitEmpresa ? todas.filter((g) => g.cuit_empresa === cuitEmpresa) : todas),
    [todas, cuitEmpresa],
  );

  // Agrupación por empresa (SPEC §8.6): el personal trabaja una empresa a la vez.
  const grupos = useMemo(() => {
    const byEmpresa = new Map<string, Gestion[]>();
    for (const g of visibles) {
      const arr = byEmpresa.get(g.cuit_empresa) ?? [];
      arr.push(g);
      byEmpresa.set(g.cuit_empresa, arr);
    }
    return Array.from(byEmpresa.entries())
      .map(([cuit, gestiones]) => ({
        cuit,
        razon: gestiones[0]?.razon_social || cuit,
        gestiones: gestiones
          .slice()
          .sort((a, b) => a.detectado_en.localeCompare(b.detectado_en)),
      }))
      .sort((a, b) => a.razon.localeCompare(b.razon));
  }, [visibles]);

  const handleConfirm = () => {
    if (!confirmTarget) return;
    marcarMutation.mutate(confirmTarget.gestion_id, {
      onSettled: () => setConfirmTarget(null),
    });
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Gestiones de Holistor"
        subtitle="Datos maestros faltantes detectados por el RPA. Dalos de alta en Holistor y marcá cada gestión como hecha."
      />

      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-56">
            <Select
              label="Estado"
              value={estado}
              onChange={(e) => setEstado(e.target.value as GestionEstado | "")}
              options={[
                { value: "", label: "Todos los estados" },
                { value: "pendiente", label: "Pendiente" },
                { value: "realizada", label: "Realizada" },
                { value: "verificada", label: "Verificada" },
                { value: "verificacion_fallida", label: "Verificación fallida" },
              ]}
            />
          </div>
          <div className="w-72">
            <Select
              label="Empresa"
              value={cuitEmpresa}
              onChange={(e) => setCuitEmpresa(e.target.value)}
              options={[
                { value: "", label: "Todas las empresas" },
                ...empresas.map((e) => ({ value: e.cuit, label: e.razon })),
              ]}
            />
          </div>
        </div>
      </Card>

      {gestionesQuery.isLoading ? (
        <div className="flex justify-center py-12">
          <Spinner size="lg" />
        </div>
      ) : gestionesQuery.isError ? (
        <Alert variant="error">
          {gestionesQuery.error.message || "Error al cargar las gestiones."}
        </Alert>
      ) : visibles.length === 0 ? (
        <Card>
          <p className="py-8 text-center text-gray-500">
            No hay gestiones que coincidan con el filtro.
          </p>
        </Card>
      ) : (
        <div className="space-y-6">
          {grupos.map((grupo) => (
            <Card key={grupo.cuit}>
              <div className="mb-3 flex items-baseline justify-between">
                <h3 className="text-lg font-semibold text-gray-900">{grupo.razon}</h3>
                <span className="text-sm text-gray-500">
                  CUIT {grupo.cuit} · {grupo.gestiones.length} gestión
                  {grupo.gestiones.length === 1 ? "" : "es"}
                </span>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableCell header>Tipo</TableCell>
                    <TableCell header>Descripción</TableCell>
                    <TableCell header>Detectado</TableCell>
                    <TableCell header>COEs</TableCell>
                    <TableCell header>Estado</TableCell>
                    <TableCell header>Acción</TableCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {grupo.gestiones.map((g) => {
                    const puedeMarcar =
                      g.estado === "pendiente" || g.estado === "verificacion_fallida";
                    return (
                      <TableRow key={g.gestion_id}>
                        <TableCell>
                          <Badge variant="default" className="whitespace-nowrap">
                            {TIPO_LABEL[g.tipo]}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <div className="text-gray-900">{g.descripcion}</div>
                          {g.estado === "verificacion_fallida" &&
                          g.verificacion_detalle ? (
                            <div className="mt-1 text-sm text-red-600">
                              {g.verificacion_detalle}
                            </div>
                          ) : null}
                          {g.estado === "realizada" && g.realizada_por ? (
                            <div className="mt-1 text-sm text-gray-500">
                              Marcada por {g.realizada_por}
                            </div>
                          ) : null}
                        </TableCell>
                        <TableCell>{formatDateTime(g.detectado_en)}</TableCell>
                        <TableCell>
                          <CoesCell coes={g.coes_afectados} />
                        </TableCell>
                        <TableCell>
                          <EstadoBadge estado={g.estado} />
                        </TableCell>
                        <TableCell>
                          {puedeMarcar ? (
                            <Button
                              variant="primary"
                              size="sm"
                              onClick={() => setConfirmTarget(g)}
                            >
                              Marcar como hecha
                            </Button>
                          ) : null}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </Card>
          ))}
        </div>
      )}

      <ConfirmModal
        isOpen={confirmTarget !== null}
        onClose={() => setConfirmTarget(null)}
        onConfirm={handleConfirm}
        title="Marcar gestión como hecha"
        message={
          confirmTarget
            ? `Confirmás que ya diste de alta en Holistor: ${confirmTarget.descripcion}. El RPA lo verificará en la próxima sincronización.`
            : ""
        }
        confirmLabel="Marcar como hecha"
        cancelLabel="Cancelar"
        variant="primary"
        isLoading={marcarMutation.isPending}
        errorMessage={marcarMutation.isError ? marcarMutation.error.message : undefined}
      />
    </div>
  );
}
