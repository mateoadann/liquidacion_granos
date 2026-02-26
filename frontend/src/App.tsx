import { useMutation } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  wslpgDummy,
  wslpgLiquidacionXCoe,
  wslpgLiquidacionXNroOrden,
  wslpgUltimoNroOrden,
} from "./api/client";
import { useHealth } from "./hooks/useHealth";

type JsonRecord = Record<string, unknown>;

function ResponsePanel({ title, data }: { title: string; data: unknown }) {
  return (
    <section className="mt-4 rounded-lg bg-white p-4 shadow-sm border border-slate-200">
      <h3 className="font-semibold text-slate-800">{title}</h3>
      <pre className="mt-2 rounded bg-slate-900 text-slate-100 p-3 text-xs overflow-auto max-h-[420px]">
        {JSON.stringify(data, null, 2)}
      </pre>
    </section>
  );
}

export default function App() {
  const { data: healthData, isLoading: healthLoading } = useHealth();
  const [ptoEmision, setPtoEmision] = useState("1");
  const [nroOrden, setNroOrden] = useState("1");
  const [coe, setCoe] = useState("");
  const [pdf, setPdf] = useState<"S" | "N">("N");
  const [lastResponse, setLastResponse] = useState<{
    title: string;
    payload: unknown;
  } | null>(null);

  const setResponse = (title: string, payload: unknown) =>
    setLastResponse({ title, payload });

  const dummyMutation = useMutation({
    mutationFn: wslpgDummy,
    onSuccess: (data) => setResponse("dummy", data),
    onError: (err: Error) => setResponse("dummy (error)", { error: err.message }),
  });

  const ultimoNroMutation = useMutation({
    mutationFn: (vars: { ptoEmision: number }) =>
      wslpgUltimoNroOrden(vars.ptoEmision),
    onSuccess: (data) =>
      setResponse("liquidacionUltimoNroOrdenConsultar", data),
    onError: (err: Error) =>
      setResponse("liquidacionUltimoNroOrdenConsultar (error)", {
        error: err.message,
      }),
  });

  const xNroMutation = useMutation({
    mutationFn: (vars: { ptoEmision: number; nroOrden: number }) =>
      wslpgLiquidacionXNroOrden(vars.ptoEmision, vars.nroOrden),
    onSuccess: (data) => setResponse("liquidacionXNroOrdenConsultar", data),
    onError: (err: Error) =>
      setResponse("liquidacionXNroOrdenConsultar (error)", {
        error: err.message,
      }),
  });

  const xCoeMutation = useMutation({
    mutationFn: (vars: { coe: number; pdf: "S" | "N" }) =>
      wslpgLiquidacionXCoe(vars.coe, vars.pdf),
    onSuccess: (data) => setResponse("liquidacionXCoeConsultar", data),
    onError: (err: Error) =>
      setResponse("liquidacionXCoeConsultar (error)", { error: err.message }),
  });

  const anyLoading = useMemo(
    () =>
      dummyMutation.isPending ||
      ultimoNroMutation.isPending ||
      xNroMutation.isPending ||
      xCoeMutation.isPending,
    [
      dummyMutation.isPending,
      ultimoNroMutation.isPending,
      xNroMutation.isPending,
      xCoeMutation.isPending,
    ]
  );

  return (
    <main className="mx-auto max-w-5xl p-6">
      <h1 className="text-2xl font-bold text-slate-900">
        WSLPG - MVP extracción
      </h1>
      <p className="mt-1 text-slate-600">
        Prueba simple de métodos: dummy, último nro orden, consulta por nro orden
        y consulta por COE.
      </p>

      <section className="mt-4 rounded-lg bg-white p-4 shadow-sm border border-slate-200">
        <h2 className="font-semibold text-slate-800">Estado backend</h2>
        {healthLoading ? (
          <p className="mt-2 text-slate-600">Consultando health...</p>
        ) : (
          <pre className="mt-2 rounded bg-slate-900 text-slate-100 p-3 text-xs overflow-auto">
            {JSON.stringify(healthData, null, 2)}
          </pre>
        )}
      </section>

      <section className="mt-4 grid gap-4 md:grid-cols-2">
        <div className="rounded-lg bg-white p-4 shadow-sm border border-slate-200">
          <h3 className="font-semibold text-slate-800">1) dummy</h3>
          <button
            className="mt-3 rounded bg-blue-600 px-3 py-2 text-white disabled:opacity-50"
            onClick={() => dummyMutation.mutate()}
            disabled={anyLoading}
          >
            Ejecutar dummy
          </button>
        </div>

        <div className="rounded-lg bg-white p-4 shadow-sm border border-slate-200">
          <h3 className="font-semibold text-slate-800">
            2) liquidacionUltimoNroOrdenConsultar
          </h3>
          <label className="mt-3 block text-sm text-slate-700">Punto emisión</label>
          <input
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
            value={ptoEmision}
            onChange={(e) => setPtoEmision(e.target.value)}
          />
          <button
            className="mt-3 rounded bg-blue-600 px-3 py-2 text-white disabled:opacity-50"
            onClick={() =>
              ultimoNroMutation.mutate({ ptoEmision: Number(ptoEmision) })
            }
            disabled={anyLoading}
          >
            Consultar último nro orden
          </button>
        </div>

        <div className="rounded-lg bg-white p-4 shadow-sm border border-slate-200">
          <h3 className="font-semibold text-slate-800">
            3) liquidacionXNroOrdenConsultar
          </h3>
          <label className="mt-3 block text-sm text-slate-700">Punto emisión</label>
          <input
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
            value={ptoEmision}
            onChange={(e) => setPtoEmision(e.target.value)}
          />
          <label className="mt-3 block text-sm text-slate-700">Nro orden</label>
          <input
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
            value={nroOrden}
            onChange={(e) => setNroOrden(e.target.value)}
          />
          <button
            className="mt-3 rounded bg-blue-600 px-3 py-2 text-white disabled:opacity-50"
            onClick={() =>
              xNroMutation.mutate({
                ptoEmision: Number(ptoEmision),
                nroOrden: Number(nroOrden),
              })
            }
            disabled={anyLoading}
          >
            Consultar por nro orden
          </button>
        </div>

        <div className="rounded-lg bg-white p-4 shadow-sm border border-slate-200">
          <h3 className="font-semibold text-slate-800">
            4) liquidacionXCoeConsultar
          </h3>
          <label className="mt-3 block text-sm text-slate-700">COE</label>
          <input
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
            value={coe}
            onChange={(e) => setCoe(e.target.value)}
          />
          <label className="mt-3 block text-sm text-slate-700">PDF</label>
          <select
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
            value={pdf}
            onChange={(e) => setPdf(e.target.value as "S" | "N")}
          >
            <option value="N">N (sin pdf)</option>
            <option value="S">S (con pdf)</option>
          </select>
          <button
            className="mt-3 rounded bg-blue-600 px-3 py-2 text-white disabled:opacity-50"
            onClick={() => xCoeMutation.mutate({ coe: Number(coe), pdf })}
            disabled={anyLoading}
          >
            Consultar por COE
          </button>
        </div>
      </section>

      {lastResponse ? (
        <ResponsePanel
          title={`Resultado: ${lastResponse.title}`}
          data={lastResponse.payload as JsonRecord}
        />
      ) : null}
    </main>
  );
}

