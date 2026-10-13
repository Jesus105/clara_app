# Operación y despliegue

## Entorno

| Variable | Uso |
|---|---|
| `DATABASE_URL` | PostgreSQL en Render/Docker. SQLite únicamente local. |
| `OPENROUTER_API_KEY` | Secreto del LLM; alias local compatible `OPENROUTERKEY`. |
| `OPENROUTER_MODEL` | Por defecto `google/gemini-2.5-flash-lite`; lista económica restringida. |
| `LLM_MAX_TOTAL_USD` | Tope, máximo permitido por configuración: 3. |
| `DEMO_PASSWORD` | Contraseña compartida del workspace de demo. |
| `SESSION_SECRET` | Secreto aleatorio de al menos 32 caracteres. Cambiarlo invalida sesiones. |
| `COOKIE_SECURE` | `true` en HTTPS publicado; `false` local. |
| `ALLOWED_ORIGINS` | Orígenes exactos separados por coma. |
| `BACKGROUND_WORKER` | `true` en Render Free; `false` cuando hay worker separado. |
| `SEED_DEMO` | Crea ejemplos ficticios una sola vez. |
| `FRONTEND_DIR` | Build estático; Docker configura `/app/frontend/dist`. |
| `RENDER_API_KEY` | Solo para `scripts/deploy.py`, nunca se envía al runtime; alias `RENDER`. |

## Publicar

1. Sube el estado probado a la rama `main` del repo.
2. Configura las dos claves en `.env` local. Nunca lo subas.
3. Ejecuta `scripts/deploy.py provision-db`. Crea exclusivamente PostgreSQL Free con acceso externo bloqueado.
4. Cuando la base esté `available`, ejecuta `deploy`. Genera contraseña y secreto si faltan, y los guarda en `.env`. Crea Web Service Free con build Docker; no habilita servicios de pago.
5. Consulta `status`. Espera estado `live`, comprueba `/api/health`, inicia sesión y prueba una importación real.
6. Para actualizaciones: push a GitHub, tests y `redeploy`. Autodeploy está desactivado para controlar las publicaciones.

El script persiste IDs y URL en `.local/deployment.json`. Si se interrumpe, busca servicios por nombre y reutiliza los existentes. Ante error API informa estado y mensaje sanitizado, nunca valores de credenciales. No modifica recursos de otros nombres ni actualiza planes.

## Render gratuito

PostgreSQL Free conserva datos fuera del filesystem efímero del servidor. API y worker usan la red interna. Las migraciones se ejecutan antes de iniciar Uvicorn; si fallan no se publica una API sobre un esquema incorrecto.

Un único proceso Uvicorn facilita la cola y los límites del login. No aumentar workers del servidor sin evaluar recursos y estrategia de rate limiting. El worker espera dos segundos entre ciclos, procesa una tarea por vez y usa timeout de 60 segundos para el proveedor.

El servidor gratuito se duerme tras 15 minutos sin requests, así que la cola no tiene SLA en ausencia de tráfico. Al volver a abrir la app, despierta y continúa desde PostgreSQL. Para el video abre la URL unos minutos antes y espera a que `/api/health` responda. No se configura tráfico artificial para eludir esa limitación.

**La base gratuita creada para esta entrega vence el 12 de noviembre de 2026.** Confirma la fecha exacta en Render (`expiresAt`) y exporta antes. Free no proporciona backups automáticos; no se contratará un plan de pago sin nueva autorización. [Límites oficiales](https://render.com/docs/free).

## Diagnóstico

| Síntoma | Acción |
|---|---|
| Página de espera de Render | Puede estar despertando; espera aproximadamente un minuto y recarga. |
| Login 401 | Usa el `DEMO_PASSWORD` de entorno; no la API key. |
| Login 429 | Espera un minuto después de intentos fallidos. |
| Análisis pendiente | Mantén la app abierta; revisa la cola y disponibilidad de la API. |
| Key inválida / HTTP 401 | Corrige el secreto del backend y reintenta la tarea fallida. |
| HTTP 402 o límite de US$3 | Revisa créditos/tope en OpenRouter. No aumentar el presupuesto de esta demo. |
| HTTP 429/5xx | El worker reintenta con backoff; después aparece en tareas fallidas. |
| JSON inválido / cita no verificable | Reintentos limitados, sin resultados inventados; reduce/clarifica la fuente. |
| Fuente descartada | Revisa dominio, correo personal, empresa y longitud del texto. |
| Aprobación 409 | Recarga el borrador; alguien cambió su revisión o estado. |
| Aprobación sin destinatario | Importa un contacto con correo corporativo; no se inventa. |
| Base vencida | Exporta antes del vencimiento; después requiere un plan de pago para recuperarla dentro del plazo de Render. |

## Respaldar sin publicar secretos

Desde Render, habilita temporalmente acceso externo únicamente a tu IP y copia la URL externa a una variable local. Con PostgreSQL CLI:

```bash
pg_dump "$CLARA_DATABASE_URL" --format=custom --file=clara-backup.dump
```

Guarda el dump fuera de Git, cifra el archivo si contiene contactos reales y vuelve a bloquear acceso externo. Para restaurar, usa `pg_restore` en otra base PostgreSQL compatible. Antes de migrar un esquema, conserva una copia y prueba la migración en una base de staging.

## Compatibilidad y siguiente etapa

Python 3.12, Node.js 22, PostgreSQL 16. Backend y frontend incluyen versiones restringidas y lockfile de npm; CI comprueba builds. Docker separa etapas y ejecuta el runtime como usuario sin privilegios. El frontend puede alojarse en Vercel con el proxy incluido, pero la entrega actual usa el mismo origen de FastAPI.

Para producción permanente hace falta definir alojamiento financiado, backups, identidad individual, controles de acceso y límites por usuario. Las integraciones reales deben verificar firmas de Slack, usar OAuth de HubSpot y conservar la aprobación humana antes de cualquier acción externa.

