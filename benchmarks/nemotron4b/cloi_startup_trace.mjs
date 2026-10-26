#!/usr/bin/env node
/** Passive trace for original Cloi CLI startup. No monkey-patching or secrets.

    Node's public diagnostics_channel API observes Undici/fetch lifecycle without
    modifying request/response, source code, timeouts, or tool behavior.
    Only allowlisted Ollama API route labels and stage names are printed.
*/
import dc from 'node:diagnostics_channel';

const routes = new Set(['/api/tags', '/api/show', '/api/chat', '/api/generate']);
const emitted = new Map();
let count = 0;
const stamp = () => Math.round(performance.now());

function emit(event, request, detail = '') {
  const path = request?.path;
  if (!routes.has(path)) return;
  console.error('STARTUP_TRACE ' + JSON.stringify({
    event, route: path, ms: stamp(), index: count++, ...(detail ? { detail } : {}),
  }));
  emitted.set(path, (emitted.get(path) || 0) + 1);
}

dc.subscribe('undici:request:create', ({ request }) =>
  emit('request_created', request));
dc.subscribe('undici:request:headers', ({ request, response }) =>
  emit('response_headers', request, String(response?.statusCode ?? 'unknown')));
dc.subscribe('undici:request:trailers', ({ request }) =>
  emit('response_trailers', request));
dc.subscribe('undici:request:error', ({ request, error }) =>
  emit('request_error', request, error?.name ?? 'Error'));

console.error('STARTUP_TRACE ' + JSON.stringify({
  event: 'cli_module_bootstrap', ms: stamp(), index: count++,
}));
// No timer: event-loop side effects could change the behavior being measured.
