#!/usr/bin/env node
/** Passive tracing for pinned Cloi CLI via Node's public diagnostics_channel.

    No monkey-patches, model prompts, URLs outside the local Ollama route set,
    HTTP headers, message bodies, or secrets are recorded.
*/
import dc from 'node:diagnostics_channel';

const routes = new Set(['/api/tags', '/api/show', '/api/chat', '/api/generate']);
const requestIds = new WeakMap();
let nextId = 0;
const stamp = () => Math.round(performance.now());
const safeErrorCode = (value) =>
  typeof value === 'string' && /^[A-Z0-9_]{1,60}$/.test(value)
    ? value : null;

function observe(event, request, response, error) {
  const route = request?.path;
  if (!routes.has(route)) return;
  let id = requestIds.get(request);
  if (id == null) {
    id = ++nextId;
    requestIds.set(request, id);
  }
  const frame = {
    event, route, request_id: id, ms: stamp(),
  };
  if (event === 'response_headers')
    frame.status = Number(response?.statusCode ?? 0);
  if (event === 'request_error') {
    frame.error_name = String(error?.name || 'Error').slice(0, 48);
    frame.error_code = safeErrorCode(error?.code || error?.cause?.code);
  }
  console.error('STARTUP_TRACE ' + JSON.stringify(frame));
}

dc.subscribe('undici:request:create', ({ request }) =>
  observe('request_created', request));
dc.subscribe('undici:request:bodySent', ({ request }) =>
  observe('request_body_sent', request));
dc.subscribe('undici:request:headers', ({ request, response }) =>
  observe('response_headers', request, response));
dc.subscribe('undici:request:trailers', ({ request }) =>
  observe('response_trailers', request));
dc.subscribe('undici:request:error', ({ request, error }) =>
  observe('request_error', request, null, error));

console.error('STARTUP_TRACE ' + JSON.stringify({
  event: 'cli_module_bootstrap', ms: stamp(),
}));
