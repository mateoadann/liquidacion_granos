from __future__ import annotations

from enum import Enum


class ExtractionPhase(str, Enum):
    LAUNCHING_BROWSER = "LAUNCHING_BROWSER"
    LOGIN_START = "LOGIN_START"
    LOGIN_CONFIRMED = "LOGIN_CONFIRMED"
    SEARCH_SERVICE = "SEARCH_SERVICE"
    OPEN_SERVICE = "OPEN_SERVICE"
    SELECT_EMPRESA = "SELECT_EMPRESA"
    OPEN_CONSULTA_RECIBIDAS = "OPEN_CONSULTA_RECIBIDAS"
    LISTING_COES = "LISTING_COES"
    DOWNLOADING_COE = "DOWNLOADING_COE"
    SAVING_TO_WS = "SAVING_TO_WS"
    FINISHED = "FINISHED"


PHASE_MESSAGES_ES: dict[ExtractionPhase, str] = {
    ExtractionPhase.LAUNCHING_BROWSER: "Iniciando navegador...",
    ExtractionPhase.LOGIN_START: "Ingresando a ARCA con clave fiscal...",
    ExtractionPhase.LOGIN_CONFIRMED: "Sesión confirmada en ARCA.",
    ExtractionPhase.SEARCH_SERVICE: "Buscando el servicio Liquidación primaria de granos...",
    ExtractionPhase.OPEN_SERVICE: "Abriendo el servicio en ARCA...",
    ExtractionPhase.SELECT_EMPRESA: "Seleccionando empresa representada...",
    ExtractionPhase.OPEN_CONSULTA_RECIBIDAS: "Abriendo consulta de liquidaciones recibidas...",
    ExtractionPhase.LISTING_COES: "Leyendo COEs encontrados en el período...",
    ExtractionPhase.DOWNLOADING_COE: "Descargando COE desde el web service de ARCA...",
    ExtractionPhase.SAVING_TO_WS: "Guardando datos del COE...",
    ExtractionPhase.FINISHED: "Extracción finalizada.",
}
