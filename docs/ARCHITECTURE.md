# Arquitectura y decisiones

## Componentes

- **React + Vite + TypeScript + Tailwind:** dashboard, ingesta, revisión y representación interactiva de Slack. FastAPI entrega el build estático para compartir origen y cookie.
- **FastAPI + SQLAlchemy + PostgreSQL:** estado transaccional, fuentes, borradores, decisiones y cola. Alembic gestiona migraciones. SQLite solo facilita desarrollo y pruebas locales.
- **Worker:** usa PostgreSQL como cola, `FOR UPDATE SKIP LOCKED` y actualización condicional para reclamar tareas. Un proceso de worker por demo. Docker soporta separación de API/worker; Render gratuito los comparte.
- **OpenRouter:** API Chat Completions vía HTTP. Modelo económico explícito, JSON validado por Pydantic. No se utiliza auto-routing a modelos de pago más caros ni se habilita búsqueda web.

## Persistencia

| Tabla | Responsabilidad |
|---|---|
| `leads` | Identidad del contacto (email o dominio), empresa, owner, score y estado |
| `sources` | Texto original y hash único de identidad + contenido normalizado |
| `signals` | Tipo, cita, fuente y puntos al momento de analizar |
| `drafts` | Un borrador por prospecto, revisión y marca de edición |
| `jobs` | Intentos, estado, lease, próxima ejecución y traza de input/output |
| `deliveries` | Snapshot inmutable del mensaje aprobado; único por prospecto |
| `audit_events` | Quién hizo qué, cuándo y con qué detalle |
| `configuration` | Reglas, reserva presupuestal y marcador de seed |

Las fuentes precargadas y los correos `.example` son ficticios. Se conservan esos datos para que la interfaz muestre un recorrido útil antes de una importación real. El seed no consume tokens y es idempotente.

## Confiabilidad

Se filtran dominios personales antes de gastar tokens. El LLM ve fuentes como datos no confiables, no instrucciones. Cada señal debe tener un ID de fuente válido y una cita continua que aparezca en esa fuente; se normalizan espacios, mayúsculas y acentos para la comparación. Esto comprueba trazabilidad de la cita, no la veracidad externa del texto importado ni la clasificación semántica del modelo.

El score se calcula por reglas y deduplica tipos. Sin señales, el prospecto queda `discarded`. No se trata una respuesta inválida como una señal válida.

Cada tarea tiene lease de cinco minutos. Tras un reinicio las tareas antiguas se recuperan. Los errores 408/429/5xx, timeouts, JSON inválido o evidencia no verificable reintentan hasta tres veces, con `max(5 × 2^intento, Retry-After)`. 401/402 o configuración inválida requieren acción humana. Las fallidas siguen en base de datos como una dead-letter queue consultable desde Actividad. Reiniciar tras una caída puede repetir una generación cuya respuesta no se guardó; la reserva conservadora contempla ese caso.

La aprobación bloquea el prospecto y comprueba su revisión. Después guarda en una transacción estado, delivery único, snapshot del correo y auditoría. Repetir una aprobación devuelve el mismo delivery. Editar luego de aprobar o rechazar un aprobado devuelve 409.

## Costos y controles

Tope: US$3. Reserva: US$0.02 por intento. La fila del presupuesto se bloquea y los intentos fallidos conservan su reserva. Se consulta el consumo agregado de la key antes de la solicitud y el catálogo de precios actual. Se limita el input a 24,000 bytes UTF-8 y salida a 1,800 tokens; se usa un límite conservador de tokens de entrada basado en bytes más margen. Si el costo máximo no cabe en la reserva o el proveedor no permite verificar consumo/precio, la llamada se detiene.

La app guarda el costo exacto cuando OpenRouter lo reporta; costo/reservas y consumo global son conceptos diferentes. El consumo global incorpora otros usos de la misma key. Un tope configurado también en OpenRouter y una key exclusiva son necesarios para un límite global fuerte frente a clientes externos.

## Seguridad y alcance

Las claves se leen desde entorno y nunca se incluyen en build frontend, cookies o logs. `.env`, `.local`, bases y secretos están excluidos de Git y del contexto Docker. El login utiliza contraseña de workspace y cookie firmada HttpOnly; producción obliga a cambiar credenciales por defecto y cookie Secure. Una cookie firmada no cifra su contenido, que solo incluye la identidad de demo.

Los textos y prompts pueden contener datos personales: las rutas protegidas entregan solo lo necesario para la revisión. Las trazas completas están en base de datos, no en el endpoint de cola. El código no visita URLs importadas ni ejecuta instrucciones de las fuentes. No hay scraping ni enriquecimiento externos.

El producto es una demo de entrevista: un usuario lógico compartido, sin SSO, RBAC, multitenancy, borrado de datos, backups automáticos o SLA. Slack, HubSpot, Langfuse, PostHog, Apollo/Clay y warehouse no están conectados; las métricas y auditoría locales permiten mostrar el flujo y preparar adaptadores futuros.

