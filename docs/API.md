# Contrato de API · v1

Base: `/api`. Documentación OpenAPI interactiva: `/api/docs`. Todas las rutas de datos requieren cookie de sesión; solo `/health` y `/auth/login` son públicas. Las respuestas no contienen API keys. Errores usan `{"detail":"Mensaje en español"}`.

## Sesión

| Método / ruta | Entrada | Resultado |
|---|---|---|
| `POST /auth/login` | `{"password":"..."}` | Cookie firmada por ocho horas, nombre y rol |
| `GET /auth/me` | Cookie | Nombre y rol del SDR de demo |
| `POST /auth/logout` | Cookie | Elimina la sesión |
| `GET /health` | Ninguna | Verifica conexión SQL; `status: ok` |

Login: cinco intentos fallidos por minuto por IP, en memoria del único proceso de demo. No es un sistema de identidad multiusuario. Requests de modificación con Origin externo se rechazan. En producción se usa TLS y cookie Secure; CORS limita orígenes configurados.

## Ingesta

### `POST /ingestions/csv/preview`

Multipart: `file`. Devuelve `columns`, `mapping`, `sample` (cinco primeras filas), `total`. Acepta coma/punto y coma/tab, UTF-8 BOM o Latin-1. Máximo 2 MB, 300 filas, 30 encabezados únicos.

### `POST /ingestions/csv`

Multipart: mismo `file`, y `mapping` como JSON serializado. Campos: `company`, `email`, `domain`, `contact`, `country`, `employees`, `content`. Obligatorios: empresa, correo **o** dominio y texto de la señal. El usuario confirma el mapeo antes de procesar.

### `POST /ingestions/text`

```json
{
  "company": "Empresa de ejemplo",
  "domain": "empresa.example",
  "contact": "Ana López",
  "email": "ana@empresa.example",
  "country": "México",
  "kind": "hiring",
  "content": "La empresa busca un Finance Manager para centralizar el control de gastos corporativos."
}
```

`kind`: `news`, `hiring`, `email`, `text`. Texto: 20–12,000 caracteres. Contacto/email opcionales; sin email no se permite aprobar la inscripción. No se inventa el destinatario.

Todas las importaciones devuelven:

```json
{
  "accepted": [{"id": "uuid", "company": "Empresa de ejemplo"}],
  "duplicates": [{"row": 3, "company": "Duplicado", "reason": "Fuente ya importada."}],
  "rejected": [{"row": 4, "company": "Personal", "reason": "Correo personal fuera del perfil B2B."}]
}
```

La respuesta confirma la cola, no la generación terminada. Consulta `/jobs` o `/leads/{id}`. El hash de identidad + texto normalizado evita repetir la misma fuente. Una nueva fuente se agrega al prospecto pendiente; los aprobados/rechazados no se reabren. Si hay análisis en curso, la fuente se reporta como duplicado con motivo explícito y se puede importar al terminar.

## Prospectos y decisiones

| Método / ruta | Comportamiento |
|---|---|
| `GET /leads?q=&status=&min_score=` | Hasta 1,000 resultados, score descendente. Incluye señales y borrador. |
| `GET /leads/{id}` | Agrega fuentes originales y estado de inscripción simulada. |
| `PATCH /leads/{id}/draft` | `subject`, `body`, `revision`; solo estado `ready`. Incrementa revisión. |
| `POST /leads/{id}/approve` | `{"revision":1}`; requiere email y borrador vigente. Guarda snapshot y auditoría. |
| `POST /leads/{id}/reject` | Solo `ready`; rechazo repetido es idempotente. |

Una revisión antigua devuelve **409**. Una aprobación repetida devuelve el mismo `delivery_id` y `already_approved: true`. El constraint único por prospecto y el lock de fila en PostgreSQL protegen contra duplicaciones concurrentes. Inscripción: `enrolled_simulated`; no existe envío real.

Estados: `pending` → `ready`/`discarded`/`failed`; `ready` → `approved`/`rejected`. Nuevas fuentes pueden volver a poner en `pending` los estados no terminales. `discarded` significa ausencia de señales verificables, no un error del sistema.

## Cola, reglas y observabilidad

| Método / ruta | Comportamiento |
|---|---|
| `GET /jobs` | Últimas 200 tareas; intentos, siguiente ejecución, error y metadatos de modelo/tokens/costo. |
| `POST /jobs/{id}/retry` | Reinicia una tarea fallida; rechaza prospectos terminales o tareas activas existentes. |
| `GET /rules` | Pesos, umbral DM y guía comercial vigente. |
| `PUT /rules` | Objeto completo validado; pesos 0–60, dominio 0–20, umbral 1–100. |
| `GET /metrics` | Conteos, siete días de tendencia, aprobación media y consumo/reservas. |
| `GET /audit` | Últimos 200 eventos con actor, fecha y detalle. |

`avg_approval_seconds` aproxima velocidad desde ingesta a aprobación. Incluye ejemplos identificados como demo y no equivale a un primer contacto real. `demo_leads` permite identificar la proporción de datos ficticios.

