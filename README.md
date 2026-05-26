# Liquidación de Granos

Sistema de gestión y auditoría de **Liquidaciones Primarias de Granos (LPG)** ante ARCA/AFIP, pensado para acopios y empresas del sector agropecuario que necesitan centralizar la consulta, descarga y control de comprobantes electrónicos del Web Service WSLPG.

La aplicación se conecta a los servicios de ARCA usando las credenciales de cada cliente y permite:

- **Extracción automatizada** de liquidaciones por rango de fechas vía Web Service y automatización de navegador.
- **Carga manual de COE** consultando primero la información en ARCA y persistiéndola opcionalmente como liquidación pendiente.
- **Control y auditoría**: marcar liquidaciones como revisadas, descargar PDF oficial, exportar a CSV/XLSX y mantener trazabilidad de quién hizo qué.
- **Multi-cliente** con certificados y claves fiscales gestionados de forma segura (cifrado en base de datos).

## Stack

Flask + PostgreSQL + Redis (backend) · React + Vite + TanStack Query (frontend) · Playwright para automatización · Docker Compose para desarrollo.
