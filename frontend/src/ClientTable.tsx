import type { Client } from "./clients";

interface ClientTableProps {
  clients: Client[];
  isLoading: boolean;
  search: string;
  onSearchChange: (value: string) => void;
  onNewClient: () => void;
  onRunPlaywright: () => void;
  runPlaywrightDisabled: boolean;
  onEdit: (client: Client) => void;
  onCertificates: (client: Client) => void;
  onValidate: (client: Client) => void;
  onExportCoes: (client: Client) => void;
  onDeactivate: (client: Client) => void;
  actionDisabled: boolean;
}

export default function ClientTable({
  clients,
  isLoading,
  search,
  onSearchChange,
  onNewClient,
  onRunPlaywright,
  runPlaywrightDisabled,
  onEdit,
  onCertificates,
  onValidate,
  onExportCoes,
  onDeactivate,
  actionDisabled,
}: ClientTableProps) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-2xl font-semibold text-slate-900">Clientes</h2>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onRunPlaywright}
            disabled={runPlaywrightDisabled}
            className="rounded-md border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-semibold text-blue-700 disabled:opacity-50"
          >
            Ejecutar Playwright
          </button>
          <button
            type="button"
            onClick={onNewClient}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
          >
            Nuevo cliente
          </button>
        </div>
      </div>

      <div className="mt-4">
        <input
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Buscar por empresa o CUIT"
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </div>

      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full border-collapse text-sm">
          <thead>
            <tr className="bg-slate-100 text-left text-slate-700">
              <th className="px-3 py-2 font-semibold">Empresa</th>
              <th className="px-3 py-2 font-semibold">CUIT</th>
              <th className="px-3 py-2 font-semibold">CUIT representado</th>
              <th className="px-3 py-2 font-semibold">Ambiente</th>
              <th className="px-3 py-2 font-semibold">Activo</th>
              <th className="px-3 py-2 font-semibold">Credenciales</th>
              <th className="px-3 py-2 font-semibold">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={7} className="px-3 py-5 text-slate-500">
                  Cargando clientes...
                </td>
              </tr>
            ) : clients.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-3 py-5 text-slate-500">
                  No hay clientes cargados
                </td>
              </tr>
            ) : (
              clients.map((client) => (
                <tr key={client.id} className="border-t border-slate-200 align-top">
                  <td className="px-3 py-2">{client.empresa}</td>
                  <td className="px-3 py-2">{client.cuit}</td>
                  <td className="px-3 py-2">{client.cuitRepresentado}</td>
                  <td className="px-3 py-2">{client.ambiente}</td>
                  <td className="px-3 py-2">{client.activo ? "Sí" : "No"}</td>
                  <td className="px-3 py-2 text-xs">
                    <p>
                      Clave fiscal: {client.claveFiscalCargada ? "cargada" : "no"}
                    </p>
                    <p>
                      Certificados: {client.certificadosCargados ? "cargados" : "no"}
                    </p>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => onEdit(client)}
                        disabled={actionDisabled}
                        className="text-blue-700 hover:underline disabled:opacity-50"
                      >
                        Editar
                      </button>
                      <button
                        type="button"
                        onClick={() => onCertificates(client)}
                        disabled={actionDisabled}
                        className="text-blue-700 hover:underline disabled:opacity-50"
                      >
                        Certificados
                      </button>
                      <button
                        type="button"
                        onClick={() => onValidate(client)}
                        disabled={actionDisabled}
                        className="text-blue-700 hover:underline disabled:opacity-50"
                      >
                        Validar
                      </button>
                      <button
                        type="button"
                        onClick={() => onExportCoes(client)}
                        disabled={actionDisabled}
                        className="text-blue-700 hover:underline disabled:opacity-50"
                      >
                        Exportar COEs
                      </button>
                      <button
                        type="button"
                        onClick={() => onDeactivate(client)}
                        disabled={actionDisabled}
                        className="text-red-700 hover:underline disabled:opacity-50"
                      >
                        Desactivar
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
