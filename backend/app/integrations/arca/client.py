from __future__ import annotations

import datetime as dt
import decimal
import inspect
import os
from dataclasses import dataclass
from typing import Any


class ArcaIntegrationError(RuntimeError):
    """Error funcional para integración ARCA."""


@dataclass
class ArcaDiscoveryConfig:
    cuit_representada: str | None
    environment: str
    wsdl_url: str | None
    service_name: str
    cert_path: str | None
    key_path: str | None
    key_passphrase: str | None
    ta_path: str | None

    @classmethod
    def from_env(cls) -> "ArcaDiscoveryConfig":
        environment = os.getenv("ARCA_ENVIRONMENT", "homologacion")
        service_name = os.getenv("ARCA_SERVICE_NAME", "wslpg")
        wsdl_url = _sanitize_wsdl_url(os.getenv("ARCA_WSDL_URL"))
        if not wsdl_url:
            wsdl_url = _default_wsdl_for(service_name=service_name, environment=environment)

        return cls(
            cuit_representada=os.getenv("ARCA_CUIT_REPRESENTADA"),
            environment=environment,
            wsdl_url=wsdl_url,
            service_name=service_name,
            cert_path=_sanitize_fs_path(os.getenv("ARCA_CERT_PATH"), "ARCA_CERT_PATH"),
            key_path=_sanitize_fs_path(os.getenv("ARCA_KEY_PATH"), "ARCA_KEY_PATH"),
            key_passphrase=os.getenv("ARCA_KEY_PASSPHRASE"),
            ta_path=_sanitize_fs_path(os.getenv("ARCA_TA_PATH"), "ARCA_TA_PATH"),
        )


def _default_wsdl_for(service_name: str, environment: str) -> str | None:
    """
    Intenta resolver un WSDL por defecto a partir de arca_arg.settings.
    Hoy priorizamos WSLPG; para otros servicios se recomienda ARCA_WSDL_URL explícito.
    """
    try:
        import arca_arg.settings as settings  # type: ignore
    except Exception:
        return None

    env_hom = environment != "produccion"
    wsdl_map = {
        "wslpg": ("WSDL_LPG_HOM", "WSDL_LPG_PROD"),
        "ws_sr_constancia_inscripcion": ("WSDL_CONSTANCIA_HOM", "WSDL_CONSTANCIA_PROD"),
    }
    pair = wsdl_map.get(service_name)
    if pair:
        return getattr(settings, pair[0] if env_hom else pair[1], None)
    return None


def _sanitize_wsdl_url(value: str | None) -> str | None:
    """
    Normaliza errores frecuentes en .env:
    - ARCA_WSDL_URL=ARCA_WSDL_URL=https://...
    - https:/... (una sola barra) -> https://...
    - comillas sobrantes.
    """
    if not value:
        return None

    v = value.strip().strip('"').strip("'")

    if "ARCA_WSDL_URL=" in v:
        v = v.split("ARCA_WSDL_URL=", 1)[1].strip()

    if v.startswith("https:/") and not v.startswith("https://"):
        v = v.replace("https:/", "https://", 1)
    if v.startswith("http:/") and not v.startswith("http://"):
        v = v.replace("http:/", "http://", 1)

    return v or None


def _sanitize_fs_path(value: str | None, var_name: str) -> str | None:
    """
    Normaliza rutas de .env y resuelve casos comunes:
    - ARCA_KEY_PATH=ARCA_KEY_PATH=data/archivo.key
    - data/archivo.key -> /app/data/archivo.key (en Docker)
    """
    if not value:
        return None

    v = value.strip().strip('"').strip("'")

    marker = f"{var_name}="
    if marker in v:
        v = v.split(marker, 1)[1].strip()

    if not v:
        return None

    if os.path.isabs(v):
        return v

    candidates = [v, os.path.join("/app", v)]
    if v.startswith("data/"):
        candidates.append(os.path.join("/app", v))
    else:
        candidates.append(os.path.join("/app/data", os.path.basename(v)))

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    # Si no existe aún (por ej. carpeta TA), devolvemos normalizado.
    if v.startswith("data/"):
        return os.path.join("/app", v)
    return v


class ArcaWslpgClient:
    """
    Adaptador de arca_arg para discovery y ejecución de métodos WSLPG.

    La librería arca_arg puede variar entre versiones, por lo que este adaptador
    construye el cliente de manera flexible usando introspección.
    """

    def __init__(self, config: ArcaDiscoveryConfig | None = None):
        self.config = config or ArcaDiscoveryConfig.from_env()
        self._client: Any | None = None
        self._ws_class: type | None = None

    # -------------------------
    # Inicialización / conexión
    # -------------------------
    def connect(self) -> Any:
        if self._client is not None:
            return self._client

        ws_class = self._resolve_ws_class()
        self._ws_class = ws_class
        self._validate_arca_inputs()
        self._configure_arca_settings_module()
        self._client = self._build_client(ws_class)
        self._run_optional_login(self._client)
        return self._client

    def _validate_arca_inputs(self) -> None:
        missing: list[str] = []
        if not self.config.wsdl_url:
            missing.append("ARCA_WSDL_URL")
        if not self.config.cuit_representada:
            missing.append("ARCA_CUIT_REPRESENTADA")
        if not self.config.cert_path:
            missing.append("ARCA_CERT_PATH")
        if not self.config.key_path:
            missing.append("ARCA_KEY_PATH")
        if not self.config.ta_path:
            missing.append("ARCA_TA_PATH")

        if missing:
            raise ArcaIntegrationError(
                f"Faltan variables ARCA requeridas: {', '.join(missing)}"
            )

        if not os.path.isfile(self.config.cert_path):  # type: ignore[arg-type]
            raise ArcaIntegrationError(
                self._build_missing_file_message(
                    "ARCA_CERT_PATH", self.config.cert_path  # type: ignore[arg-type]
                )
            )
        if not os.path.isfile(self.config.key_path):  # type: ignore[arg-type]
            raise ArcaIntegrationError(
                self._build_missing_file_message(
                    "ARCA_KEY_PATH", self.config.key_path  # type: ignore[arg-type]
                )
            )

        # TA puede no existir: la creamos si hace falta.
        ta_path = self.config.ta_path  # type: ignore[assignment]
        try:
            os.makedirs(ta_path, exist_ok=True)  # type: ignore[arg-type]
        except Exception as exc:
            raise ArcaIntegrationError(
                f"No se pudo crear/usar ARCA_TA_PATH='{ta_path}'. Revisá permisos de escritura."
            ) from exc

    def _build_missing_file_message(self, var_name: str, path: str) -> str:
        available = []
        for base in ("/app/data", "data", "."):
            try:
                if os.path.isdir(base):
                    entries = sorted(os.listdir(base))
                    preview = ", ".join(entries[:10])
                    if len(entries) > 10:
                        preview += ", ..."
                    available.append(f"{base}: [{preview}]")
            except Exception:
                continue

        hint = " | ".join(available) if available else "sin carpetas de referencia visibles"
        return (
            f"{var_name} apunta a '{path}' pero el archivo no existe dentro del contenedor. "
            f"Revisá .env y volumen ./data -> /app/data. Detectado: {hint}"
        )

    def _resolve_ws_class(self) -> type:
        try:
            from arca_arg.webservice import ArcaWebService

            return ArcaWebService
        except Exception:
            pass

        try:
            from arca_arg import ArcaWebService  # type: ignore

            return ArcaWebService
        except Exception as exc:
            raise ArcaIntegrationError(
                "No se pudo importar ArcaWebService desde arca_arg."
            ) from exc

    def _configure_arca_settings_module(self) -> None:
        """
        arca_arg usa variables globales en arca_arg.settings para auth (cert/key/ta/cuit/prod).
        Las seteamos antes de construir ArcaWebService.
        """
        try:
            import arca_arg.settings as settings  # type: ignore
        except Exception as exc:
            raise ArcaIntegrationError(
                "No se pudo importar arca_arg.settings para configurar credenciales."
            ) from exc

        prod_mode = self.config.environment == "produccion"
        wsaa_wsdl = settings.WSDL_WSAA_PROD if prod_mode else settings.WSDL_WSAA_HOM

        # 1) Actualizar settings (fuente base)
        if self.config.cert_path:
            settings.CERT_PATH = self.config.cert_path
        if self.config.key_path:
            settings.PRIVATE_KEY_PATH = self.config.key_path
        if self.config.ta_path:
            settings.TA_FILES_PATH = self.config.ta_path
        if self.config.cuit_representada:
            settings.CUIT = self.config.cuit_representada
        settings.PROD = prod_mode

        # 2) Parchear módulos que importan constantes "by value"
        #    auth.py: from .settings import CERT_PATH, PRIVATE_KEY_PATH, ..., PROD, TA_FILES_PATH
        #    webservice.py: from .settings import CUIT
        try:
            import arca_arg.auth as auth_module  # type: ignore

            if self.config.cert_path:
                auth_module.CERT_PATH = self.config.cert_path
            if self.config.key_path:
                auth_module.PRIVATE_KEY_PATH = self.config.key_path
            if self.config.ta_path:
                auth_module.TA_FILES_PATH = self.config.ta_path
            auth_module.PROD = prod_mode
            auth_module.WSDL_WSAA = wsaa_wsdl
        except Exception:
            # Si no se puede parchear, seguimos: settings ya está configurado.
            pass

        try:
            import arca_arg.webservice as webservice_module  # type: ignore

            if self.config.cuit_representada:
                webservice_module.CUIT = self.config.cuit_representada
        except Exception:
            pass

    def _build_client(self, ws_class: type) -> Any:
        signature = inspect.signature(ws_class)
        kwargs = self._build_kwargs(signature)

        try:
            return ws_class(**kwargs)
        except TypeError as exc:
            raise ArcaIntegrationError(
                f"No se pudo instanciar ArcaWebService con kwargs detectados: {kwargs}. "
                f"Firma detectada: {signature}"
            ) from exc

    def _build_kwargs(self, signature: inspect.Signature) -> dict[str, Any]:
        mapping: dict[str, Any] = {
            "wsdl_url": self.config.wsdl_url,
            "wsdl": self.config.wsdl_url,
            "service": self.config.service_name,
            "ws": self.config.service_name,
            "ws_name": self.config.service_name,
            "webservice": self.config.service_name,
            "service_name": self.config.service_name,
            "cuit": self.config.cuit_representada,
            "cuit_representada": self.config.cuit_representada,
            "environment": self.config.environment,
            "env": self.config.environment,
            "production": self.config.environment == "produccion",
            "cert": self.config.cert_path,
            "certificate": self.config.cert_path,
            "cert_path": self.config.cert_path,
            "key": self.config.key_path,
            "private_key": self.config.key_path,
            "key_path": self.config.key_path,
            "passphrase": self.config.key_passphrase,
            "key_passphrase": self.config.key_passphrase,
            "ta_path": self.config.ta_path,
            "ta_folder": self.config.ta_path,
            "cache_dir": self.config.ta_path,
        }

        kwargs: dict[str, Any] = {}
        accepts_var_kwargs = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in signature.parameters.values()
        )

        for name, param in signature.parameters.items():
            if name == "self":
                continue

            if name in mapping and mapping[name] is not None:
                kwargs[name] = mapping[name]
                continue

            if param.default is inspect._empty and not accepts_var_kwargs:
                raise ArcaIntegrationError(
                    f"Falta valor requerido para construir ArcaWebService: '{name}'. "
                    f"Definí las variables ARCA_* necesarias."
                )

        if accepts_var_kwargs:
            for key, value in mapping.items():
                if value is not None and key not in kwargs:
                    kwargs[key] = value

        return kwargs

    def _run_optional_login(self, client: Any) -> None:
        # Algunas versiones de arca_arg requieren login/auth explícito.
        candidate_methods = ("login", "authenticate", "auth")

        for method_name in candidate_methods:
            method = getattr(client, method_name, None)
            if not callable(method):
                continue

            signature = inspect.signature(method)
            kwargs: dict[str, Any] = {}
            for name in signature.parameters:
                if name in {"self"}:
                    continue
                if name in {"service", "ws", "ws_name", "webservice"}:
                    kwargs[name] = self.config.service_name
                elif name in {"environment", "env"}:
                    kwargs[name] = self.config.environment

            try:
                method(**kwargs)
            except TypeError:
                # Si la firma no matchea, dejamos que el cliente opere sin login explícito.
                pass
            except Exception as exc:
                raise ArcaIntegrationError(
                    f"Fallo en login/auth con método '{method_name}'."
                ) from exc
            return

    # -------------------------
    # API de uso
    # -------------------------
    def list_methods(self) -> list[str]:
        client = self.connect()
        if not hasattr(client, "list_methods"):
            raise ArcaIntegrationError("ArcaWebService no expone list_methods().")
        methods = client.list_methods()
        if isinstance(methods, (tuple, set)):
            return sorted(list(methods))
        if isinstance(methods, list):
            return sorted(methods)
        return sorted(list(methods or []))

    def method_help(self, method_name: str) -> Any:
        client = self.connect()
        if not hasattr(client, "method_help"):
            raise ArcaIntegrationError("ArcaWebService no expone method_help().")
        return client.method_help(method_name)

    def get_type(self, type_name: str) -> Any:
        client = self.connect()
        if not hasattr(client, "get_type"):
            raise ArcaIntegrationError("ArcaWebService no expone get_type().")
        return client.get_type(type_name)

    def send_request(self, method_name: str, data: dict) -> Any:
        client = self.connect()
        if not hasattr(client, "send_request"):
            raise ArcaIntegrationError("ArcaWebService no expone send_request().")
        return client.send_request(method_name, data)

    def get_auth_payload(self) -> dict[str, Any]:
        client = self.connect()
        token = getattr(client, "token", None)
        sign = getattr(client, "sign", None)
        cuit = self.config.cuit_representada or getattr(client, "cuit", None)
        if not token or not sign or not cuit:
            raise ArcaIntegrationError(
                "No se pudo construir auth (token/sign/cuit). Revisá autenticación WSAA."
            )
        return {"token": token, "sign": sign, "cuit": int(str(cuit))}

    def call_dummy(self) -> dict[str, Any]:
        response = self.send_request("dummy", {})
        return self._serialize_response(response)

    def call_liquidacion_ultimo_nro_orden(self, pto_emision: int) -> dict[str, Any]:
        payload = {"auth": self.get_auth_payload(), "ptoEmision": int(pto_emision)}
        response = self.send_request("liquidacionUltimoNroOrdenConsultar", payload)
        return self._serialize_response(response)

    def call_liquidacion_x_nro_orden(
        self, pto_emision: int, nro_orden: int
    ) -> dict[str, Any]:
        payload = {
            "auth": self.get_auth_payload(),
            "ptoEmision": int(pto_emision),
            "nroOrden": int(nro_orden),
        }
        response = self.send_request("liquidacionXNroOrdenConsultar", payload)
        return self._serialize_response(response)

    def call_liquidacion_x_coe(self, coe: int, pdf: str = "N") -> dict[str, Any]:
        value = (pdf or "N").upper()
        if value not in {"S", "N"}:
            raise ArcaIntegrationError("pdf debe ser 'S' o 'N'.")
        payload = {"auth": self.get_auth_payload(), "coe": int(coe), "pdf": value}
        response = self.send_request("liquidacionXCoeConsultar", payload)
        return self._serialize_response(response)

    def call_ajuste_x_coe(self, coe: int, pdf: str = "N") -> dict[str, Any]:
        value = (pdf or "N").upper()
        if value not in {"S", "N"}:
            raise ArcaIntegrationError("pdf debe ser 'S' o 'N'.")
        payload = {"auth": self.get_auth_payload(), "coe": int(coe), "pdf": value}
        response = self.send_request("ajusteXCoeConsultar", payload)
        return self._serialize_response(response)

    def discovery_summary(self) -> dict[str, Any]:
        methods = self.list_methods()
        return {
            "service": self.config.service_name,
            "environment": self.config.environment,
            "wsdl_url": self.config.wsdl_url,
            "total_methods": len(methods),
            "methods": methods,
        }

    def _serialize_response(self, value: Any) -> dict[str, Any]:
        return _safe_serialize(value)


class ArcaConstanciaClient(ArcaWslpgClient):
    """Cliente para ws_sr_constancia_inscripcion (padrón AFIP A5)."""

    def __init__(self, config: ArcaDiscoveryConfig | None = None):
        cfg = config or ArcaDiscoveryConfig.from_env()
        cfg.service_name = "ws_sr_constancia_inscripcion"
        if not cfg.wsdl_url or "wslpg" in (cfg.wsdl_url or ""):
            cfg.wsdl_url = _default_wsdl_for("ws_sr_constancia_inscripcion", cfg.environment)
        super().__init__(cfg)

    def get_persona(self, cuit: int | str) -> dict[str, Any]:
        """Consulta datos de un contribuyente por CUIT usando getPersona_v2."""
        payload = {
            "token": self.get_auth_payload()["token"],
            "sign": self.get_auth_payload()["sign"],
            "cuitRepresentada": int(self.config.cuit_representada or 0),
            "idPersona": int(cuit),
        }
        response = self.send_request("getPersona_v2", payload)
        return self._serialize_response(response)

    def extract_persona_info(self, cuit: int | str) -> dict[str, Any]:
        """Consulta y extrae los campos relevantes del contribuyente."""
        raw = self.get_persona(cuit)
        data = raw.get("data", {}) if isinstance(raw, dict) else {}

        persona = data.get("personaReturn", data)
        if not isinstance(persona, dict):
            persona = {}

        datos_gen = persona.get("datosGenerales", {}) or {}
        domicilio = datos_gen.get("domicilioFiscal", {}) or {}

        # Razón social o nombre+apellido
        razon_social = datos_gen.get("razonSocial") or ""
        if not razon_social:
            nombre = datos_gen.get("nombre", "") or ""
            apellido = datos_gen.get("apellido", "") or ""
            razon_social = f"{apellido} {nombre}".strip()

        # IVA: buscar en datosRegimenGeneral.impuesto o datosMonotributo.impuesto
        condicion_iva = self._extract_condicion_iva(persona)

        return {
            "cuit": str(datos_gen.get("idPersona", cuit)),
            "razonSocial": razon_social,
            "domicilio": domicilio.get("direccion", ""),
            "localidad": domicilio.get("localidad", ""),
            "provincia": domicilio.get("descripcionProvincia", ""),
            "codigoPostal": domicilio.get("codPostal", ""),
            "condicionIva": condicion_iva,
            "tipoPersona": datos_gen.get("tipoPersona", ""),
            "estadoClave": datos_gen.get("estadoClave", ""),
        }

    def _extract_condicion_iva(self, persona: dict) -> str:
        """Extrae la condición frente al IVA del contribuyente."""
        # Si tiene datosRegimenGeneral con IVA activo → Responsable Inscripto
        regimen = persona.get("datosRegimenGeneral", {}) or {}
        impuestos = regimen.get("impuesto", [])
        if isinstance(impuestos, dict):
            impuestos = [impuestos]
        for imp in impuestos:
            if not isinstance(imp, dict):
                continue
            if str(imp.get("idImpuesto")) == "30" and imp.get("estadoImpuesto") == "AC":
                return "Responsable Inscripto"

        # Si es monotributista
        mono = persona.get("datosMonotributo", {}) or {}
        if mono.get("categoriaMonotributo") or mono.get("actividadMonotributista"):
            return "Monotributo"

        # IVA inactivo u otra situación
        for imp in impuestos:
            if not isinstance(imp, dict):
                continue
            if str(imp.get("idImpuesto")) == "30":
                return "Exento"

        return ""


def _safe_serialize(value: Any) -> dict[str, Any]:
    try:
        from zeep.helpers import serialize_object  # type: ignore

        serialized = serialize_object(value)
        return {"data": _normalize_json_safe(serialized)}
    except Exception:
        return {"data": _normalize_json_safe(value)}


def _normalize_json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    if isinstance(value, dict):
        return {str(k): _normalize_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_json_safe(v) for v in value]
    if hasattr(value, "__dict__"):
        return _normalize_json_safe(vars(value))
    return str(value)
