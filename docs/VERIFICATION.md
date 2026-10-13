# Verificación de la entrega · 13 de octubre de 2026

URL: https://clara-deal-signals.onrender.com

## Resultados

| Comprobación | Resultado |
|---|---|
| Backend | 24 pruebas aprobadas: sesión, CSRF, CSV, deduplicación, score, revisiones, idempotencia, cola, lease, errores del modelo y presupuesto. |
| Frontend | TypeScript y build de producción aprobados. |
| Navegador | 4 recorridos aprobados: búsqueda/evidencia/edición/aprobación, CSV, inbox de Slack y móvil/configuración/auditoría. |
| GitHub Actions | Workflow `Quality checks` aprobado en GitHub. |
| Render | Web Service `free`, PostgreSQL `free`, deploy `live`, `/api/health` responde `ok`. |
| Navegador publicado | Login, dashboard, formulario de fuentes y móvil sin errores JavaScript; sin overflow horizontal a 390 px. |
| IA real | CSV de seis filas: tres prospectos aceptados, un duplicado y dos descartes. Generación real de señales y borrador con Gemini 2.5 Flash Lite. |
| Decisión humana | Correo editado y aprobado en el servidor; segunda aprobación devuelve el mismo delivery. Auditoría y snapshot conservados en PostgreSQL. |

El primer análisis real (Vela Systems) devolvió score **100**, citas verificadas y borrador con **391 tokens de entrada**, **453 de salida**, **2,204 ms** de latencia y costo reportado **US$0.0002203**. Es un dato de una ejecución, no un SLA ni una garantía de latencia.

Datos importados para la verificación: empresas ficticias y correos `.example`. La generación usa un LLM real. Slack y HubSpot son simulaciones; la aprobación no produjo correos ni mensajes externos.

## Reproducir

```bash
.venv/bin/pytest backend/tests -q
npm --prefix frontend run build
cd frontend && npm run test:e2e
# Desde la raíz, con DEMO_PASSWORD en .env:
.venv/bin/python scripts/smoke.py
.venv/bin/python scripts/deploy.py status
```

El smoke real reutiliza contactos ya importados y comprueba el estado final. Las pruebas automatizadas usan datos temporales y mocks del LLM; no requieren secretos ni consumen tokens.

## Límites comprobados y pendientes de producción permanente

Las pruebas verifican el control de gasto de la aplicación. Para imponer un límite global a cualquier cliente que use la key se necesita también configurar su límite en OpenRouter. La cuenta tiene un presupuesto autorizado de US$3; la aplicación no puede aumentarlo por configuración.

Render gratuito no garantiza disponibilidad continua: despierta después de inactividad y la base vence a los 30 días. No se han conectado los adaptadores reales de Slack/HubSpot ni probado envíos reales. No se presenta esta entrega como infraestructura con SLA de producción.

