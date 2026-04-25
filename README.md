# irvinbot-gateway

API Gateway de Irvinbot. Es el único punto de entrada para el frontend. Valida tokens JWT, enruta requests a los microservicios correspondientes y propaga información del usuario via headers. Corre en el **puerto 8000**.

---

## Qué hace

- Recibe **todas** las peticiones del frontend en `http://gateway:8000/api/*`
- Valida el token JWT en todas las rutas excepto login y registro
- Inyecta headers `X-User-ID`, `X-User-Email`, `X-User-Role` en cada request hacia los servicios
- Hace proxy transparente a auth (8001), chat (8002) y docs (8003)
- Soporta SSE streaming para el endpoint de chat
- Devuelve `503` si un servicio está caído

El gateway **no tiene base de datos**. Es stateless.

---

## Tabla de enrutamiento

| Path del frontend | Servicio destino | URL interna |
|-------------------|-----------------|-------------|
| `POST /api/auth/login` | auth | `http://auth:8001/auth/login` |
| `POST /api/auth/register` | auth | `http://auth:8001/auth/register` |
| `GET /api/auth/me` | auth | `http://auth:8001/auth/me` |
| `POST /api/auth/refresh` | auth | `http://auth:8001/auth/refresh` |
| `GET /api/chat/sessions` | chat | `http://chat:8002/chat/sessions` |
| `POST /api/chat/sessions/{id}/stream` | chat | `http://chat:8002/chat/sessions/{id}/stream` |
| `POST /api/docs/upload` | docs | `http://docs:8003/docs/upload` |
| `GET /api/docs/` | docs | `http://docs:8003/docs/` |

La regla es simple: `/api/{service}/{path}` → `http://{service}:{port}/{service}/{path}`.

---

## Cómo funciona internamente

```
Request HTTP → gateway_router.py
  ├── ¿es ruta pública? (login/register)
  │     └── SÍ → proxy.forward() directamente
  │     └── NO → security.require_auth(Authorization header)
  │               ├── token inválido → HTTP 401
  │               └── token válido → extrae {sub, email, role}
  │                     └── añade X-User-ID, X-User-Email, X-User-Role
  │                           └── proxy.forward()
  │
  └── proxy.forward()
        ├── ¿termina en "stream"? → StreamingResponse (SSE pass-through)
        └── request normal → httpx.AsyncClient → Response
```

### Manejo de SSE (streaming)

Para el endpoint `/api/chat/sessions/{id}/stream`, el gateway detecta que el path termina en `"stream"` y usa `httpx.stream()` en lugar de una request normal. Los chunks del LLM pasan directamente al frontend sin bufferizarse.

---

## Rutas públicas (sin JWT)

Solo estas dos rutas no requieren token:

```python
# app/core/security.py
_PUBLIC_ROUTES = {
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/register"),
}
```

Para añadir más rutas públicas (ej. verificación de email), agregar la tupla `(method, path)` a ese set.

---

## Estructura de archivos

```
irvinbot-gateway/
├── main.py                      ← FastAPI app, CORS, monta router en /api
├── Dockerfile
├── requirements.txt
├── .env.example
└── app/
    ├── api/
    │   └── gateway_router.py    ← catch-all /{service}/{path:path}
    ├── proxy/
    │   └── proxy.py             ← forward(), _stream_response()
    └── core/
        ├── config.py            ← URLs de los servicios
        └── security.py          ← is_public(), require_auth(), decode_token()
```

---

## Variables de entorno

| Variable | Descripción | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Para validar JWT (misma que auth) | `change-me-in-production` |
| `ALGORITHM` | Algoritmo JWT | `HS256` |
| `AUTH_SERVICE_URL` | URL del servicio auth | `http://localhost:8001` |
| `CHAT_SERVICE_URL` | URL del servicio chat | `http://localhost:8002` |
| `DOCS_SERVICE_URL` | URL del servicio docs | `http://localhost:8003` |

> En Docker, las URLs usan el nombre del contenedor: `http://auth:8001`, `http://chat:8002`, `http://docs:8003`.

---

## Headers que el gateway inyecta

Cuando el token es válido, el gateway añade estos headers a cada request hacia los servicios:

| Header | Valor | Ejemplo |
|--------|-------|---------|
| `X-User-ID` | UUID del usuario | `3f4a1b2c-...` |
| `X-User-Email` | Email del usuario | `maria@uni.edu` |
| `X-User-Role` | Rol del usuario | `student` |

Los servicios de chat y docs **no dependen** de estos headers (cada uno decodifica el JWT por su cuenta), pero están disponibles si algún servicio necesita el user_id sin hacer la decodificación.

---

## Errores devueltos por el gateway

| Código | Causa |
|--------|-------|
| `401` | Token ausente, malformado o expirado |
| `404` | Servicio desconocido en la URL (ej: `/api/payments/...`) |
| `503` | Servicio destino no responde (`ConnectError`) |

---

## Cómo correr localmente

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8000
```

Los servicios de auth, chat y docs deben estar corriendo para que el proxy funcione.

### Correr tests
```bash
pytest app/tests/ -v
# Los tests usan respx para mockear httpx, no necesitan los servicios levantados
```

---

## Cómo extender este servicio

**Añadir rate limiting:**
```python
# main.py
from slowapi import Limiter
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# En el router:
@router.api_route(...)
@limiter.limit("60/minute")
async def route(...): ...
```

**Añadir logging centralizado:**
En `proxy.py`, loguear cada request con `user_id`, `service`, `path`, `status_code` y `latency` antes de devolver la respuesta.

**Añadir un nuevo microservicio:**
1. Crear la URL en `app/core/config.py` (ej. `NOTIFICATIONS_SERVICE_URL`)
2. Añadir la entrada en `_SERVICE_MAP` en `app/proxy/proxy.py`:
   ```python
   "notifications": lambda: settings.NOTIFICATIONS_SERVICE_URL + "/notifications",
   ```
3. Listo. El catch-all enrutará automáticamente `/api/notifications/*`.
