# Rediseño de UI - Documento de Diseño

**Fecha:** 2026-03-05
**Estado:** Aprobado
**Enfoque:** Incremental con Tailwind puro

## Resumen Ejecutivo

Rediseño completo del frontend para el sistema de Liquidación de Granos. La aplicación pasará de una única página a un sistema multi-página con autenticación, navegación, y nuevas funcionalidades para visualización de COEs y gestión de usuarios.

### Contexto del Negocio

- **Dominio:** Gestión de documentos para comercialización de granos (productor ↔ acopio)
- **Usuarios:** Personal administrativo (no técnico)
- **Estilo visual:** Moderno/minimalista con acentos verdes (campo)
- **Exposición:** App expuesta a internet (requiere seguridad robusta)

---

## Arquitectura de Páginas y Navegación

### Estructura de Rutas

```
/login                  → Página de login (pública)
/                       → Home/Dashboard (protegida)
/clientes               → Gestión de clientes (protegida)
/clientes/:id           → Detalle/edición de cliente
/coes                   → Listado de COEs con filtros (protegida)
/coes/:id               → Detalle de COE individual
/exportar               → Exportación de COEs por cliente (protegida)
/configuracion          → Configuración general (protegida, solo admin)
/configuracion/usuarios → CRUD de usuarios (protegida, solo admin)
```

### Layout Principal

```
┌─────────────────────────────────────────────────────────┐
│  Logo   │  Home  │ Clientes │ COEs │ Exportar │ Config │ Usuario ▼ │
├─────────────────────────────────────────────────────────┤
│                                                         │
│                    Contenido de página                  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

- Navbar horizontal superior
- Logo + nombre a la izquierda
- Links de navegación centrados
- Dropdown de usuario a la derecha (nombre, cerrar sesión)
- React Router v6 para routing
- Componente `<ProtectedRoute>` para rutas autenticadas

---

## Sistema de Autenticación

### Modelo de Usuario

```python
# Tabla: users
id: int (PK)
username: str (unique, not null)
password_hash: str (bcrypt, not null)
nombre: str (not null)
rol: enum('admin', 'usuario') (default: 'usuario')
activo: bool (default: True)
created_at: datetime
updated_at: datetime
last_login_at: datetime (nullable)
```

### Endpoints de Auth

| Método | Ruta | Descripción | Acceso |
|--------|------|-------------|--------|
| POST | `/api/auth/login` | Login con username/password, retorna JWT | Público |
| POST | `/api/auth/logout` | Invalida token (blacklist en Redis) | Autenticado |
| GET | `/api/auth/me` | Retorna usuario actual | Autenticado |
| POST | `/api/auth/refresh` | Renueva JWT antes de expirar | Autenticado |

### Medidas de Seguridad

- **JWT con expiración corta** (15 minutos) + refresh token (7 días)
- **Bcrypt** para hash de contraseñas (cost factor 12)
- **Rate limiting** en `/api/auth/login` (5 intentos por minuto por IP)
- **HTTPS obligatorio** en producción
- **Cookies HttpOnly + Secure + SameSite=Strict** para refresh token
- **Headers de seguridad**: CORS restringido, X-Content-Type-Options, X-Frame-Options
- **Blacklist de tokens** en logout (usando Redis)

### Flujo de Auth en Frontend

1. Usuario ingresa username/password en `/login`
2. Backend valida, retorna `access_token` (JWT) en body + `refresh_token` en cookie HttpOnly
3. Frontend guarda `access_token` en memoria (Zustand) - NO localStorage
4. Cada request incluye header `Authorization: Bearer <token>`
5. Si token expira (401), intenta refresh automático
6. Si refresh falla, redirige a `/login`

### Roles y Permisos

| Rol | Permisos |
|-----|----------|
| `admin` | Todo: CRUD usuarios, ver todos los clientes/COEs, configuración |
| `usuario` | Ver clientes asignados, ejecutar Playwright, exportar COEs |

### Restricción de Admin

- El sistema **siempre debe tener al menos 1 usuario admin activo**
- No se puede eliminar/desactivar el último admin
- No se puede cambiar el rol del último admin a "usuario"
- El backend valida esto antes de cualquier operación

---

## Sistema de Diseño Visual

### Paleta de Colores

```
Primario (verde campo):
  - green-600: #16a34a  → botones principales, links activos
  - green-700: #15803d  → hover en botones
  - green-50:  #f0fdf4  → backgrounds sutiles

Neutros (base):
  - slate-900: #0f172a  → textos principales
  - slate-600: #475569  → textos secundarios
  - slate-200: #e2e8f0  → bordes
  - slate-50:  #f8fafc  → fondo de página
  - white:     #ffffff  → cards, contenedores

Semánticos:
  - amber-500:  #f59e0b → warnings, pendiente (color trigo)
  - red-600:    #dc2626 → errores, eliminar
  - emerald-600:#059669 → éxito, confirmado
  - blue-600:   #2563eb → info, links secundarios
```

### Tipografía

- **Font:** Inter (Google Fonts)
- **Tamaños:**
  - Títulos de página: `text-2xl font-semibold`
  - Subtítulos: `text-lg font-medium`
  - Cuerpo: `text-sm` (14px)
  - Labels: `text-sm font-medium`
  - Ayudas: `text-xs text-slate-500`

### Componentes Base

```
/frontend/src/
  components/
    ui/
      Button.tsx        → variantes: primary, secondary, danger, ghost
      Input.tsx         → con label, error, helper text
      Select.tsx        → dropdown estilizado
      Card.tsx          → contenedor con sombra
      Badge.tsx         → estados (activo, pendiente, error)
      Modal.tsx         → diálogos reutilizables
      Table.tsx         → tabla con estilos consistentes
      Spinner.tsx       → loading indicator
      Alert.tsx         → mensajes success/error/warning
    layout/
      Navbar.tsx        → navegación principal
      ProtectedRoute.tsx→ wrapper de rutas autenticadas
      PageHeader.tsx    → título + acciones de página
```

### Variantes de Botón

| Variante | Uso | Estilo |
|----------|-----|--------|
| `primary` | Acción principal | Verde sólido, texto blanco |
| `secondary` | Acción secundaria | Borde verde, fondo transparente |
| `danger` | Eliminar/desactivar | Rojo sólido |
| `ghost` | Acciones menores | Solo texto, hover con fondo |

---

## Estructura de Páginas

### Login (`/login`)

- Fondo slate-50, card blanca centrada
- Logo/ícono de la app arriba
- Campos: username, password
- Mensajes de error debajo del formulario
- Sin "olvidé contraseña" (admin resetea manualmente)

### Home Dashboard (`/`)

- Cards con métricas: clientes activos, COEs totales, última extracción
- Panel principal para ejecutar Playwright
- Selección de fechas y clientes
- Estado/progreso del último job en tiempo real

### Clientes (`/clientes`)

- Buscador por empresa o CUIT
- Tabla simplificada con columnas: Empresa, CUIT, Estado, Acciones
- Menú contextual (⋮): Editar, Certificados, Validar, Ver COEs, Desactivar
- Badge de estado: verde=activo, gris=inactivo
- Click en fila → `/clientes/:id`

### COEs (`/coes`)

- Filtros: Cliente, Fecha desde/hasta, Estado
- Tabla paginada con ordenamiento por columnas
- Columnas: COE, Cliente, Fecha, Estado
- Icono de ojo → `/coes/:id` con detalle completo

### Exportar (`/exportar`)

- Wizard visual paso a paso:
  1. Seleccionar clientes (checkboxes)
  2. Rango de fechas (opcional)
  3. Formato (CSV / Excel)
- Preview de cantidad de COEs antes de descargar

### Configuración (`/configuracion`)

- Enlace a gestión de usuarios
- Espacio para futuras opciones

### Usuarios (`/configuracion/usuarios`)

- Solo accesible para rol `admin`
- Tabla: Usuario, Nombre, Rol, Estado, Acciones
- Acciones: Editar, Resetear contraseña, Desactivar
- Último admin no puede desactivarse (botón disabled + tooltip)

---

## Fases de Implementación

### Fase 1: Auth + Login + Layout base
**Branch:** `feature/003-auth-login`

**Backend:**
- Modelo `User` con migraciones
- Endpoints de auth
- Middleware JWT
- Rate limiting
- Seed de admin inicial

**Frontend:**
- React Router v6
- Página `/login`
- Componentes: `Button`, `Input`, `Alert`, `Spinner`
- `Navbar` + `ProtectedRoute`
- Store de auth (Zustand)

### Fase 2: Home Dashboard
**Branch:** `feature/004-home-dashboard`

**Backend:**
- Endpoint `/api/stats`

**Frontend:**
- Página `/` con métricas
- Panel de ejecución Playwright
- Componentes: `Card`, `Badge`, `Select`

### Fase 3: Gestión de Clientes mejorada
**Branch:** `feature/005-clientes-ui`

**Frontend:**
- Página `/clientes` mejorada
- Página `/clientes/:id`
- Componentes: `Table`, `Modal`, `Dropdown`

### Fase 4: Visualización de COEs
**Branch:** `feature/006-coes-viewer`

**Backend:**
- Endpoints `/api/coes` y `/api/coes/:id`

**Frontend:**
- Página `/coes` con filtros y paginación
- Página `/coes/:id`

### Fase 5: Exportación + Usuarios
**Branch:** `feature/007-export-users`

**Backend:**
- CRUD `/api/users` (solo admin)
- Validación último admin

**Frontend:**
- Página `/exportar` (wizard)
- Páginas `/configuracion` y `/configuracion/usuarios`

---

## Git Workflow

- Cada fase se desarrolla en su branch `feature/NNN-slug`
- Branches se crean desde `dev` actualizado
- Se integran vía PR a `dev`
- Deben pasar todos los checks de CI

---

## Testing

### Backend Tests (Auth)

- Login exitoso/fallido
- Rate limiting
- Refresh token
- Logout invalida token
- Rutas protegidas sin token → 401
- Rutas admin sin rol → 403
- CRUD usuarios
- Restricción último admin

### Seguridad Checklist

- [ ] Passwords hasheados con bcrypt (cost 12)
- [ ] JWT con expiración corta (15 min)
- [ ] Refresh token en cookie HttpOnly + Secure + SameSite
- [ ] Rate limiting en login
- [ ] CORS configurado solo para origen del frontend
- [ ] Headers de seguridad
- [ ] Validación de inputs en backend
- [ ] No exponer stack traces en producción

---

## Seed de Admin Inicial

```bash
flask create-admin --username admin --password <password> --nombre "Administrador"
```

- Falla si ya existe un admin
- Password mínimo 8 caracteres
- Se ejecuta una sola vez en primer deploy
