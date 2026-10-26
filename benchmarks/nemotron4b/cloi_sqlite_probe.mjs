#!/usr/bin/env node
/** Exercise pinned Cloi's SQLite startup code, without network or generation. */
import fs from 'node:fs';

const expectedDir = process.argv[2];
const model = process.argv[3];
if (!expectedDir || !model || process.argv.length !== 4) {
  console.error('SQLITE_PROBE_INVALID_ARGS');
  process.exitCode = 2;
} else {
  try {
    console.error('SQLITE_STAGE_NODE_STARTED');
    if (process.env.CLOI_DATA_DIR !== expectedDir) {
      throw new Error('CLOI_DATA_DIR_MISMATCH');
    }
    console.error('SQLITE_STAGE_IMPORT_BEGIN');
    const { Session } = await import('/opt/cloi/src/session/store.js');
    const { DATA_DIR, DB_PATH } = await import('/opt/cloi/src/util/paths.js');
    if (DATA_DIR !== expectedDir || DB_PATH !== expectedDir + '/cloi.db') {
      throw new Error('CLOI_UPSTREAM_PATH_MISMATCH');
    }
    console.error('SQLITE_STAGE_UPSTREAM_IMPORT_OK');
    fs.mkdirSync(DATA_DIR, { recursive: true });
    fs.writeFileSync(DATA_DIR + '/write-probe.txt', 'LOCAL27_NO_SECRETS');
    console.error('SQLITE_STAGE_FS_WRITE_OK');
    console.error('SQLITE_STAGE_SESSION_CREATE_BEGIN');
    const session = Session.create({ cwd: '/app', model });
    console.error('SQLITE_STAGE_SESSION_CREATED');
    session.addMessage({ role: 'user', content: 'LOCAL27_SYNTHETIC_DIAGNOSTIC' });
    console.error('SQLITE_STAGE_MESSAGE_PERSISTED');
    if (session.messageCount() !== 1) throw new Error('SQLITE_MESSAGE_COUNT_MISMATCH');
    console.error('SQLITE_PROBE_PASS');
  } catch (error) {
    console.error('SQLITE_PROBE_ERROR_' + (error?.name || 'Error'));
    process.exitCode = 1;
  }
}
