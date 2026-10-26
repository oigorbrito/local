#!/usr/bin/env node
/** Exercise Cloi's pinned Ollama provider preflight without a generation call.

    Bounded by the parent subprocess timeout. Print only stage labels so an
    interrupted fetch still leaves an actionable checkpoint in stderr.
 */
import { isReachable, listModels, supportsTools } from '/opt/cloi/src/provider/ollama.js';

const model = process.argv[2];
if (!model || process.argv.length !== 3) {
  console.error('PROBE_INVALID_MODEL_ARGUMENT');
  process.exitCode = 2;
} else {
  try {
    console.error('PROBE_NODE_STARTED');
    const reachable = await isReachable(3000);
    if (!reachable) {
      console.error('PROBE_TAGS_UNREACHABLE');
      process.exitCode = 1;
    } else {
      console.error('PROBE_TAGS_HTTP_OK');
      const installed = await listModels();
      console.error('PROBE_TAGS_JSON_PARSED');
      if (!installed.includes(model)) {
        console.error('PROBE_MODEL_NOT_LISTED');
        process.exitCode = 1;
      } else {
        console.error('PROBE_SHOW_REQUEST_BEGIN');
        const capable = await supportsTools(model);
        console.error('PROBE_SHOW_JSON_PARSED');
        if (!capable) {
          console.error('PROBE_MODEL_TOOLS_UNAVAILABLE');
          process.exitCode = 1;
        } else {
          console.error('PROBE_PREFLIGHT_PASS');
        }
      }
    }
  } catch (error) {
    console.error('PROBE_EXCEPTION_' + (error?.name || 'Error'));
    process.exitCode = 1;
  }
}
