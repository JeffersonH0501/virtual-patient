# Validación de preparación experimental — Paciente Virtual

Validación práctica para iniciar sesiones experimentales. Alcance: verificar el
flujo real de extremo a extremo y corregir solo bloqueadores (P0/P1). No se
hicieron refactorizaciones, cambios científicos, de UI ni de migraciones.

Entorno de validación: Docker local (`docker-compose.local.yml`), VM 8 CPU /
~7.8 GB, PostgreSQL `max_connections=100`. Credenciales Azure reales presentes en
`.env.local`. Sin cámara/micrófono/navegador interactivo disponibles en este
entorno de validación (ver NOT TESTED).

## Estado de preparación experimental

| Componente | Estado | Evidencia |
| --- | --- | --- |
| Autenticación y permisos | **PASS** | `/auth/token` devuelve JWT válido; `/users/me`, `admin/history`, `clinical-cases`, `personalities` → 200 con token, 401 sin token; admin bloqueado para crear entrevistas ("Administrators cannot start medical interview simulations"). |
| Calibración | **PASS (sintético) / NOT TESTED (captura real)** | `verify_deployment.py`: extracción nativa de audio lista (196 frames) y worker visual listo; la captura de calibración real con cámara no se pudo ejecutar aquí. |
| Entrevista clínica (turno conversacional) | **PASS (real)** | Turno real por el código de producción (`VirtualPatientController.process_user_message`) con Azure real → respuesta coherente del paciente en español, caso Diabetes, personalidad friendly_polite. Datos de prueba limpiados. |
| Captura de audio y video | **NOT TESTED (real)** | Requiere navegador + cámara/micrófono. La tubería de recepción/almacenamiento por bloques está cubierta por 33 pruebas backend (orden, offsets, Range 200/206/416, medios parciales). |
| STT | **PASS (real)** | Ruta de producción (`AzureOpenAISpeechToTextProvider`) transcribió audio TTS real: "Buenos días, doctor. Me duele la cabeza." |
| LLM | **PASS (real)** | Azure chat normal y mini OK; turno conversacional real genera respuesta en personaje. |
| TTS | **PASS (real)** | `AzureOpenAITextToSpeechProvider` sintetizó 44.928 bytes de audio real. |
| Persistencia | **PASS** | 839 pruebas backend verdes (incluye turnos, orden, aislamiento por entrevista, recuperación, cegamiento). DB sana (5 casos, 6 personalidades, 1 admin, 0 entrevistas tras reset). |
| Procesamiento multimodal | **PASS (sintético)** | `verify_deployment.py`: extracción de audio nativa y worker de video listos; API↔worker OK (singleton lock, colas, poller vivos). Procesamiento sobre medios reales de participante: NOT TESTED. |
| Evaluación automática | **PASS (real)** | `EvaluationAgent.evaluate_all_aspects` real produjo puntuaciones en las 5 categorías comunicativas (rúbrica de Bayona) con Azure real. |
| Evaluación docente | **PASS (contrato)** | 23 pruebas de `test_doctor_grading` verdes (asignación, cegamiento, calificación, permisos); flujo de UI con doctor real: NOT TESTED. |
| Consulta de resultados | **PASS (endpoints) / NOT TESTED (recap con medios reales)** | Endpoints de historial/recap/resultados responden; 33 pruebas de recap/blocks verdes. Reproducción real en navegador: NOT TESTED. |
| Workers e infraestructura | **PASS** | 4 servicios healthy (api/db/ui/worker); worker con lock singleton, colas y poller vivos; health checks 200. |
| Prueba E2E completa | **PARCIAL** | STT→LLM→TTS→evaluación verificados reales por separado y encadenados en código; la sesión completa con cámara/mic en navegador no se pudo ejecutar aquí. |

## Correcciones realizadas

### 1. Azure no se inyectaba al contenedor en ejecución (P0 — bloqueador)
- **Problema:** el contenedor `api` en ejecución reportaba todas las claves Azure
  como `MISSING`; sin ellas, STT/LLM/TTS/embeddings no funcionan → no se puede
  realizar ninguna entrevista.
- **Causa:** el `environment:` del compose fija `AZURE_OPENAI_*` con
  `${VAR:-local-not-configured}`, y ese bloque sobrescribe al `env_file`. Una
  invocación `docker compose up` directa (sin `--env-file`) deja las claves en el
  fallback. El contenedor en ejecución se había levantado así.
- **Solución (sin cambio de archivos):** relanzar por el flujo soportado
  `docker compose --env-file .env.local ...` (lo que hace `deploy-local.sh`).
  Verificado: tras relanzar, las 6 claves Azure quedan `SET` en el contenedor.
- **Pruebas:** `scripts/check_azure.py` → chat/embeddings/TTS/STT OK; turno
  conversacional real OK.
- **Instrucción de despliegue:** iniciar siempre con `bash deploy-local.sh up`
  (o `setup`), NO con `docker compose up` directo, para que las claves Azure se
  carguen desde `.env.local`.

### 2. `check_azure.py` reportaba STT como FAILED falsamente (P1 — verificación engañosa)
- **Problema:** `scripts/check_azure.py` reportaba "Azure STT: FAILED (404
  DeploymentNotFound)" aunque el STT de producción funciona. Esto podría llevar a
  concluir erróneamente que el STT no sirve.
- **Causa:** el smoke-check usaba el cliente v1 (`create_openai_client`) para STT,
  mientras que la ruta de producción usa el cliente Azure versionado
  (`create_azure_openai_client`). El endpoint v1 devuelve 404 para transcripciones.
- **Archivos modificados:** `virtual-patient-api/scripts/check_azure.py`.
- **Solución:** `check_stt` ahora crea el cliente con `create_azure_openai_client`,
  igual que el proveedor de producción. Cambio solo en la herramienta de
  verificación; no toca el flujo ni la ciencia.
- **Pruebas:** `check_azure.py` → "Azure STT: OK" + "All Azure OpenAI deployments
  passed". Sintaxis verificada.

## Verificaciones técnicas ejecutadas

- Backend: **839 pruebas, 0 fallos**.
- Frontend: `yarn build` (typecheck) OK, `yarn lint` limpio, **425 pruebas / 60
  archivos, 0 fallos**.
- `verify_deployment.py`: cases 5, personalities 6, Alembic `001_initial_schema`,
  LangGraph listo, audio nativo 196 frames, worker visual listo.
- Azure real (billable): chat normal, chat mini, embeddings, TTS, STT → todos OK.
- Health: api/ui 200, worker interno healthy (singleton lock, colas, poller).
- DB: conexión OK, pool 10+10 con pre_ping; integridad de datos semilla.

## Problemas pendientes

**P0:** ninguno conocido tras las correcciones.

**P1:**
- La configuración Azure es frágil ante una invocación `docker compose up`
  directa (queda en fallback). Mitigado por documentación (usar
  `deploy-local.sh`). Un endurecimiento opcional (mover `AZURE_OPENAI_*` fuera del
  bloque `environment` para que mande `env_file`, como ya se hizo con `ADMIN_*`)
  eliminaría el riesgo; no se aplicó para no tocar las guardas `${VAR:?}` de
  producción sin solicitarlo.

**P2 (no abordados en esta tarea, por instrucción):** consolidación de migraciones
ya hecha en sesiones previas; limpieza de código legacy; optimizaciones.

## Verificaciones manuales pendientes (requieren navegador + cámara/mic + sesión real)

1. Permisos de cámara/micrófono y manejo de permiso denegado en el navegador.
2. Calibración visual/audio real de principio a fin y su transición a la entrevista.
3. Captura real de audio/video del estudiante por bloques y su subida.
4. Sesión conversacional completa en la UI (varios turnos, sincronización en vivo).
5. Finalización real → procesamiento multimodal sobre medios reales → resultados.
6. Reproducción del recap con medios reales y consulta tras recargar/reabrir.
7. Acceso de un doctor real a sus asignaciones y calificación en la UI.
8. Comportamiento ante fallo real de proveedor externo a mitad de entrevista.

## Veredicto final

**READY WITH LIMITATIONS.**

Los componentes esenciales del flujo experimental fueron verificados con rutas de
código y proveedores reales: autenticación/autorización, generación de respuesta
del paciente (LLM), transcripción (STT), síntesis de voz (TTS), evaluación
automática (5 categorías), arranque e integración de workers, y persistencia
(839 pruebas). No quedan bloqueadores P0 conocidos.

Limitaciones que deben comunicarse antes de iniciar:
- La captura real con cámara/micrófono, la calibración real, la sesión completa en
  navegador y el procesamiento multimodal sobre medios reales **no se pudieron
  ejecutar en este entorno** (sin dispositivos ni navegador interactivo). Deben
  validarse manualmente con una sesión de prueba real (checklist arriba) antes de
  la primera sesión con participantes.
- Iniciar siempre con `bash deploy-local.sh up`/`setup` para que Azure cargue.

No se declara READY pleno porque la cadena físico-interactiva (cámara/mic →
calibración → captura → recap) no fue verificada de extremo a extremo con medios
reales en este entorno; esa es la verificación manual final pendiente.
