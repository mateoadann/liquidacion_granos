from __future__ import annotations

import csv
import io
from datetime import datetime

from flask import Blueprint, jsonify, request, send_file
from sqlalchemy import cast, Date
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import LpgDocument, Taxpayer
from ..time_utils import now_cordoba_naive
from ..middleware import require_auth
from ..services import (
    CertificateValidationError,
    decrypt_secret,
    delete_client_certificates,
    encrypt_secret,
    extract_fecha_liquidacion,
    fecha_liquidacion_expr,
    get_client_certificate_meta,
    is_placeholder_secret,
    is_valid_ambiente,
    is_valid_cuit,
    save_client_certificates,
    validate_certificate_and_key_paths,
)

clients_bp = Blueprint("clients", __name__)


def _has_clave_fiscal(item: Taxpayer) -> bool:
    if not item.clave_fiscal_encrypted:
        return False
    if is_placeholder_secret(item.clave_fiscal_encrypted):
        return False
    try:
        decrypt_secret(item.clave_fiscal_encrypted)
        return True
    except ValueError:
        return False


def _serialize_client(item: Taxpayer) -> dict:
    return {
        "id": item.id,
        "empresa": item.empresa,
        "cuit": item.cuit,
        "cuit_representado": item.cuit_representado,
        "ambiente": item.ambiente,
        "activo": item.activo,
        "playwright_enabled": item.playwright_enabled,
        "has_clave_fiscal": _has_clave_fiscal(item),
        "cert_crt_filename": item.cert_crt_filename,
        "cert_key_filename": item.cert_key_filename,
        "cert_uploaded_at": item.cert_uploaded_at.isoformat()
        if item.cert_uploaded_at
        else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _error(message: str, status_code: int = 400):
    return jsonify({"error": message}), status_code


def _parse_bool(value, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "si"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    raise ValueError(f"{field_name} debe ser booleano.")


def _parse_active_query(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "si"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ValueError("Parametro 'active' invalido. Use true o false.")


def _parse_export_date(value: str | None) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"Fecha inválida: '{text}'. Use DD/MM/AAAA o AAAA-MM-DD.")


def _safe_export_text(value: object) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return f"'{text}"
    return text


def _build_export_row(doc: LpgDocument) -> dict:
    """Construye una fila de exportación con todos los campos del COE."""
    # Use datos_limpios if available, otherwise fall back to raw_data
    dl = doc.datos_limpios or {}
    raw = doc.raw_data or {}
    data = dl if dl else (raw.get("data", raw) if isinstance(raw, dict) else {})

    # For deducciones/retenciones
    deducciones = data.get("deducciones", [])
    if not isinstance(deducciones, list):
        deducciones = []
    retenciones = data.get("retenciones", [])
    if not isinstance(retenciones, list):
        retenciones = []
    ded = deducciones[0] if deducciones else {}
    ret = retenciones[0] if retenciones else {}

    def safe(val):
        return _safe_export_text(val) if val is not None else ""

    def num(val):
        return str(val) if val is not None else ""

    return {
        # Document basics
        "coe": safe(doc.coe),
        "pto_emision": safe(doc.pto_emision),
        "nro_orden": safe(doc.nro_orden),
        "estado": safe(doc.estado),
        "created_at": doc.created_at.isoformat() if doc.created_at else "",
        # General
        "codTipoOperacion": safe(data.get("codTipoOperacion")),
        "descTipoOperacion": safe(data.get("descTipoOperacion")),
        "fechaLiquidacion": safe(extract_fecha_liquidacion(doc)),
        # Comprador/Vendedor
        "cuitComprador": safe(data.get("cuitComprador")),
        "cuitVendedor": safe(data.get("cuitVendedor")),
        # Condiciones
        "precioRefTn": num(data.get("precioRefTn")),
        "codGradoRef": safe(data.get("codGradoRef")),
        "descGradoRef": safe(data.get("descGradoRef")),
        "codGrano": safe(data.get("codGrano")),
        "descGrano": safe(data.get("descGrano")),
        "precioFleteTn": num(data.get("precioFleteTn")),
        "codPuerto": safe(data.get("codPuerto")),
        "descPuerto": safe(data.get("descPuerto")),
        # Mercaderia
        "nroCertificadoDeposito": safe(data.get("nroCertificadoDeposito")),
        "codGradoEnt": safe(data.get("codGradoEnt")),
        "descGradoEnt": safe(data.get("descGradoEnt")),
        "factorEnt": num(data.get("factorEnt")),
        "contProteico": num(data.get("contProteico")),
        "pesoNeto": num(data.get("pesoNeto")),
        "codLocalidadProcedencia": safe(data.get("codLocalidadProcedencia")),
        "codProvProcedencia": safe(data.get("codProvProcedencia")),
        "descProvProcedencia": safe(data.get("descProvProcedencia")),
        "descLocalidadProcedencia": safe(data.get("descLocalidadProcedencia")),
        # Operacion
        "totalPesoNeto": num(data.get("totalPesoNeto")),
        "precioOperacion": num(data.get("precioOperacion")),
        "subTotal": num(data.get("subTotal")),
        "alicIvaOperacion": num(data.get("alicIvaOperacion")),
        "importeIva": num(data.get("importeIva")),
        "operacionConIva": num(data.get("operacionConIva")),
        # Deduccion (primera)
        "ded_codigoConcepto": safe(ded.get("codigoConcepto")),
        "ded_descConcepto": safe(ded.get("descConcepto")),
        "ded_detalleAclaratorio": safe(ded.get("detalleAclaratorio")),
        "ded_baseCalculo": num(ded.get("baseCalculo")),
        "ded_alicuotaIva": num(ded.get("alicuotaIva")),
        "ded_importeIva": num(ded.get("importeIva")),
        "ded_importeDeduccion": num(ded.get("importeDeduccion")),
        # Retencion (primera)
        "ret_codigoConcepto": safe(ret.get("codigoConcepto")),
        "ret_descConcepto": safe(ret.get("descConcepto")),
        "ret_detalleAclaratorio": safe(ret.get("detalleAclaratorio")),
        "ret_nroCertificadoRetencion": safe(ret.get("nroCertificadoRetencion")),
        "ret_importeCertificadoRetencion": num(ret.get("importeCertificadoRetencion")),
        "ret_fechaCertificadoRetencion": safe(ret.get("fechaCertificadoRetencion")),
        "ret_baseCalculo": num(ret.get("baseCalculo")),
        "ret_alicuota": num(ret.get("alicuota")),
        "ret_importeRetencion": num(ret.get("importeRetencion")),
        # Totales
        "totalRetencionAfip": num(data.get("totalRetencionAfip")),
        "totalNetoAPagar": num(data.get("totalNetoAPagar")),
        "totalPercepcion": num(data.get("totalPercepcion")),
        "totalOtrasRetenciones": num(data.get("totalOtrasRetenciones")),
        "totalIvaRg4310_18": num(data.get("totalIvaRg4310_18")),
        "totalDeduccion": num(data.get("totalDeduccion")),
        "totalPagoSegunCondicion": num(data.get("totalPagoSegunCondicion")),
    }


# Campos para la exportación en orden
EXPORT_FIELDNAMES = [
    "coe", "pto_emision", "nro_orden", "estado", "created_at",
    "codTipoOperacion", "descTipoOperacion", "fechaLiquidacion",
    "cuitComprador", "cuitVendedor",
    "precioRefTn", "codGradoRef", "descGradoRef", "codGrano", "descGrano",
    "precioFleteTn", "codPuerto", "descPuerto",
    "nroCertificadoDeposito", "codGradoEnt", "descGradoEnt", "factorEnt", "contProteico",
    "pesoNeto", "codLocalidadProcedencia", "codProvProcedencia",
    "descProvProcedencia", "descLocalidadProcedencia",
    "totalPesoNeto", "precioOperacion", "subTotal", "alicIvaOperacion",
    "importeIva", "operacionConIva",
    "ded_codigoConcepto", "ded_descConcepto", "ded_detalleAclaratorio", "ded_baseCalculo",
    "ded_alicuotaIva", "ded_importeIva", "ded_importeDeduccion",
    "ret_codigoConcepto", "ret_descConcepto", "ret_detalleAclaratorio", "ret_nroCertificadoRetencion",
    "ret_importeCertificadoRetencion", "ret_fechaCertificadoRetencion",
    "ret_baseCalculo", "ret_alicuota", "ret_importeRetencion",
    "totalRetencionAfip", "totalNetoAPagar", "totalPercepcion",
    "totalOtrasRetenciones", "totalIvaRg4310_18", "totalDeduccion",
    "totalPagoSegunCondicion",
]


def _build_export_filename(client: Taxpayer, ext: str) -> str:
    company = "_".join((client.empresa or "cliente").split())
    safe = "".join(ch for ch in company if ch.isalnum() or ch in {"_", "-"}).strip("_")
    safe = safe or f"cliente_{client.id}"
    timestamp = now_cordoba_naive().strftime("%Y%m%d_%H%M%S")
    return f"coes_{safe}_{timestamp}.{ext}"


@clients_bp.get("/clients")
@require_auth
def list_clients():
    try:
        active = _parse_active_query(request.args.get("active"))
    except ValueError as exc:
        return _error(str(exc), 400)

    query = Taxpayer.query.order_by(Taxpayer.id.asc())
    if active is True:
        query = query.filter(Taxpayer.activo.is_(True))
    elif active is False:
        query = query.filter(Taxpayer.activo.is_(False))

    return jsonify([_serialize_client(item) for item in query.all()])


@clients_bp.post("/clients")
@require_auth
def create_client():
    payload = request.get_json(silent=True) or {}

    empresa = str(payload.get("empresa", "")).strip()
    cuit = str(payload.get("cuit", "")).strip()
    cuit_representado = str(payload.get("cuit_representado", "")).strip()
    ambiente = str(payload.get("ambiente", "homologacion")).strip().lower()
    clave_fiscal = payload.get("clave_fiscal")

    if not empresa:
        return _error("empresa es obligatoria.", 400)
    if not is_valid_cuit(cuit):
        return _error("CUIT invalida. Debe tener 11 digitos.", 400)
    if not is_valid_cuit(cuit_representado):
        return _error("cuit_representado invalido. Debe tener 11 digitos.", 400)
    if not is_valid_ambiente(ambiente):
        return _error("ambiente invalido. Valores permitidos: homologacion, produccion.", 400)
    if not isinstance(clave_fiscal, str) or not clave_fiscal.strip():
        return _error("clave_fiscal es obligatoria.", 400)
    if Taxpayer.query.filter_by(cuit=cuit).first():
        return _error("La CUIT ya existe.", 409)

    try:
        encrypted_secret = encrypt_secret(clave_fiscal)
    except ValueError as exc:
        return _error(str(exc), 400)

    item = Taxpayer()
    item.empresa = empresa
    item.cuit = cuit
    item.cuit_representado = cuit_representado
    item.ambiente = ambiente
    item.clave_fiscal_encrypted = encrypted_secret
    item.activo = True
    item.playwright_enabled = True
    db.session.add(item)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("La CUIT ya existe.", 409)

    return jsonify(_serialize_client(item)), 201


@clients_bp.get("/clients/<int:client_id>")
@require_auth
def get_client(client_id: int):
    item = Taxpayer.query.get_or_404(client_id)
    return jsonify(_serialize_client(item))


@clients_bp.patch("/clients/<int:client_id>")
@require_auth
def update_client(client_id: int):
    item = Taxpayer.query.get_or_404(client_id)
    payload = request.get_json(silent=True) or {}

    if "empresa" in payload:
        empresa = str(payload.get("empresa", "")).strip()
        if not empresa:
            return _error("empresa no puede estar vacia.", 400)
        item.empresa = empresa

    if "cuit" in payload:
        cuit = str(payload.get("cuit", "")).strip()
        if not is_valid_cuit(cuit):
            return _error("CUIT invalida. Debe tener 11 digitos.", 400)
        existing = Taxpayer.query.filter(Taxpayer.cuit == cuit, Taxpayer.id != item.id).first()
        if existing:
            return _error("La CUIT ya existe.", 409)
        item.cuit = cuit

    if "cuit_representado" in payload:
        cuit_representado = str(payload.get("cuit_representado", "")).strip()
        if not is_valid_cuit(cuit_representado):
            return _error("cuit_representado invalido. Debe tener 11 digitos.", 400)
        item.cuit_representado = cuit_representado

    if "ambiente" in payload:
        ambiente = str(payload.get("ambiente", "")).strip().lower()
        if not is_valid_ambiente(ambiente):
            return _error(
                "ambiente invalido. Valores permitidos: homologacion, produccion.", 400
            )
        item.ambiente = ambiente

    if "activo" in payload:
        try:
            item.activo = _parse_bool(payload["activo"], "activo")
        except ValueError as exc:
            return _error(str(exc), 400)

    if "playwright_enabled" in payload:
        try:
            item.playwright_enabled = _parse_bool(
                payload["playwright_enabled"], "playwright_enabled"
            )
        except ValueError as exc:
            return _error(str(exc), 400)

    if "clave_fiscal" in payload:
        clave_fiscal = payload.get("clave_fiscal")
        if not isinstance(clave_fiscal, str) or not clave_fiscal.strip():
            return _error("clave_fiscal no puede estar vacia.", 400)
        try:
            item.clave_fiscal_encrypted = encrypt_secret(clave_fiscal)
        except ValueError as exc:
            return _error(str(exc), 400)

    item.updated_at = now_cordoba_naive()

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("La CUIT ya existe.", 409)

    return jsonify(_serialize_client(item))


@clients_bp.delete("/clients/<int:client_id>")
@require_auth
def delete_client(client_id: int):
    item = Taxpayer.query.get_or_404(client_id)
    item.activo = False
    item.updated_at = now_cordoba_naive()
    db.session.commit()
    return jsonify(_serialize_client(item))


@clients_bp.post("/clients/<int:client_id>/certificates")
@require_auth
def upload_client_certificates(client_id: int):
    item = Taxpayer.query.get_or_404(client_id)

    cert_file = request.files.get("cert_file")
    key_file = request.files.get("key_file")

    if cert_file is None or key_file is None:
        return _error("Debe enviar cert_file y key_file.", 400)

    try:
        saved_meta = save_client_certificates(item.id, cert_file, key_file)
    except CertificateValidationError as exc:
        return _error(str(exc), 422)
    except ValueError as exc:
        return _error(str(exc), 400)

    item.cert_crt_path = saved_meta["cert_crt_path"]
    item.cert_key_path = saved_meta["cert_key_path"]
    item.cert_crt_filename = saved_meta["cert_crt_filename"]
    item.cert_key_filename = saved_meta["cert_key_filename"]
    item.cert_uploaded_at = now_cordoba_naive()
    item.updated_at = now_cordoba_naive()

    db.session.commit()

    return jsonify(
        {
            "client": _serialize_client(item),
            "certificates": get_client_certificate_meta(item.id),
        }
    )


@clients_bp.get("/clients/<int:client_id>/certificates/meta")
@require_auth
def get_certificates_meta(client_id: int):
    item = Taxpayer.query.get_or_404(client_id)
    storage_meta = get_client_certificate_meta(item.id)

    return jsonify(
        {
            "client_id": item.id,
            "cert_crt_filename": item.cert_crt_filename,
            "cert_key_filename": item.cert_key_filename,
            "cert_uploaded_at": item.cert_uploaded_at.isoformat()
            if item.cert_uploaded_at
            else None,
            "has_certificates": storage_meta["has_certificates"],
            "storage": storage_meta,
        }
    )


@clients_bp.delete("/clients/<int:client_id>/certificates")
@require_auth
def remove_client_certificates(client_id: int):
    item = Taxpayer.query.get_or_404(client_id)
    delete_client_certificates(item.id)

    item.cert_crt_path = None
    item.cert_key_path = None
    item.cert_crt_filename = None
    item.cert_key_filename = None
    item.cert_uploaded_at = None
    item.updated_at = now_cordoba_naive()
    db.session.commit()

    return jsonify({"ok": True, "message": "Certificados eliminados."})


@clients_bp.post("/clients/<int:client_id>/validate-config")
@require_auth
def validate_client_config(client_id: int):
    item = Taxpayer.query.get_or_404(client_id)
    storage_meta = get_client_certificate_meta(item.id)

    has_empresa = bool(item.empresa and item.empresa.strip())
    has_cuit = is_valid_cuit(item.cuit)
    has_cuit_representado = is_valid_cuit(item.cuit_representado)
    has_clave_fiscal = _has_clave_fiscal(item)
    has_certificates = bool(
        item.cert_crt_path
        and item.cert_key_path
        and storage_meta["cert_crt_exists"]
        and storage_meta["cert_key_exists"]
    )

    certificates_valid = False
    if has_certificates:
        try:
            validate_certificate_and_key_paths(item.cert_crt_path, item.cert_key_path)
            certificates_valid = True
        except CertificateValidationError:
            certificates_valid = False

    ready_for_playwright = all(
        [
            has_empresa,
            has_cuit,
            has_cuit_representado,
            has_clave_fiscal,
            has_certificates,
            certificates_valid,
            item.activo,
            item.playwright_enabled,
        ]
    )

    return jsonify(
        {
            "has_empresa": has_empresa,
            "has_cuit": has_cuit,
            "has_cuit_representado": has_cuit_representado,
            "has_clave_fiscal": has_clave_fiscal,
            "has_certificates": has_certificates,
            "certificates_valid": certificates_valid,
            "ready_for_playwright": ready_for_playwright,
        }
    )


@clients_bp.get("/clients/<int:client_id>/coes/export")
@require_auth
def export_client_coes(client_id: int):
    client = Taxpayer.query.get_or_404(client_id)
    fmt = (request.args.get("format") or "csv").strip().lower()
    if fmt not in {"csv", "xlsx"}:
        return _error("format inválido. Valores permitidos: csv, xlsx.", 400)

    try:
        fecha_desde = _parse_export_date(request.args.get("fecha_desde"))
        fecha_hasta = _parse_export_date(request.args.get("fecha_hasta"))
    except ValueError as exc:
        return _error(str(exc), 400)

    query = LpgDocument.query.filter(LpgDocument.taxpayer_id == client.id)

    fecha_liq_expr = fecha_liquidacion_expr()

    if fecha_desde:
        query = query.filter(cast(fecha_liq_expr, Date) >= fecha_desde.date())
    if fecha_hasta:
        query = query.filter(cast(fecha_liq_expr, Date) <= fecha_hasta.date())

    documents = query.order_by(cast(fecha_liq_expr, Date).asc(), LpgDocument.id.asc()).all()

    rows = [_build_export_row(doc) for doc in documents]

    if fmt == "csv":
        csv_buffer = io.StringIO()
        writer = csv.DictWriter(
            csv_buffer,
            fieldnames=EXPORT_FIELDNAMES,
        )
        writer.writeheader()
        writer.writerows(rows)

        bytes_buffer = io.BytesIO(csv_buffer.getvalue().encode("utf-8-sig"))
        bytes_buffer.seek(0)
        return send_file(
            bytes_buffer,
            mimetype="text/csv",
            as_attachment=True,
            download_name=_build_export_filename(client, "csv"),
        )

    try:
        from openpyxl import Workbook
    except ModuleNotFoundError:
        return _error(
            "No se pudo generar XLSX porque falta dependencia openpyxl en backend.",
            503,
        )

    workbook = Workbook()
    sheet = workbook.create_sheet(title="COEs", index=0)
    if "Sheet" in workbook.sheetnames:
        del workbook["Sheet"]
    sheet.append(EXPORT_FIELDNAMES)
    for row in rows:
        sheet.append([row[key] for key in EXPORT_FIELDNAMES])

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=_build_export_filename(client, "xlsx"),
    )
