#!/usr/bin/env bash
# Current regression probes: synthetic inputs, existing Docker services only.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

docker compose -f docker-compose.local.yml exec -T ui node --input-type=module <<'JS'
import fs from 'node:fs';
import ts from 'typescript';
const source = fs.readFileSync('/app/src/hooks/useInterviewRecording.ts', 'utf8');
const tree = ts.createSourceFile('capture.ts', source, ts.ScriptTarget.Latest, true);
function callback(name) {
  let result;
  function visit(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(tree) === name) result = node.initializer.arguments[0].getText(tree);
    ts.forEachChild(node, visit);
  }
  visit(tree);
  if (!result) throw new Error(`Missing production callback: ${name}`);
  return ts.transpile(`const fn = ${result};`, {target: ts.ScriptTarget.ES2022});
}
const helper = ts.transpile(fs.readFileSync('/app/src/utils/sessionClock.ts', 'utf8'), {target: ts.ScriptTarget.ES2022}).replace(/^export /gm, '');
const sessionElapsedAt = new Function(`${helper}; return sessionElapsedAt;`)();
const now = {value: 10000};
const pauses = {current: []};
const elapsedAt = new Function('originRef', 'pauseIntervalsRef', 'performance', 'sessionElapsedAt', `${callback('elapsedAt')}; return fn;`)(
  {current: 0}, pauses, {now: () => now.value}, sessionElapsedAt);
let release;
let saved;
const queue = {current: new Promise(resolve => {release = resolve;})};
const scope = {
  patientSpeakingRef: {current: true}, patientLevelTimerRef: {current: null},
  patientAnalyserRef: {current: null}, setPatientAudioLevel() {},
  patientTurnsRef: {current: new Map([[1, {sequence: 0, startedAt: 5000, transcript: 'Synthetic patient.'}]])},
  interviewId: 7, stopTurnSegment: async () => null, turnWritesRef: queue,
  saveInterviewTurn: async (...args) => {saved = args[2]; return {turnId: 'synthetic'};},
  elapsedAt, uploadTurnVideo() {}, patientRoiSamplesRef: {current: []}, setErrorCode() {},
};
const endPatientTurn = new Function(...Object.keys(scope), `${callback('endPatientTurn')}; return fn;`)(...Object.values(scope));
endPatientTurn(1, true);
now.value = 14000;
pauses.current.push({start: 12000, end: 13000});
release();
await queue.current;
if (saved.startMs !== 5000 || saved.endMs !== 10000 || elapsedAt(5000) !== 5000) throw new Error('Event time changed after queue delay or a later pause');
console.log('Event clock and delayed turn persistence: passed');
JS

docker compose -f docker-compose.local.yml exec -T api python -m pytest \
  app/routers/tests/test_managed_users.py \
  app/multimodal/tests/test_quality_policy.py \
  app/multimodal/tests/test_calibration_attestation.py \
  app/multimodal/tests/test_processing_jobs.py \
  app/media/tests/test_probe.py app/media/tests/test_retention.py -q

docker compose -f docker-compose.local.yml exec -T video-processing-worker python -m pytest \
  app/nonverbal/tests/test_preprocessing.py app/nonverbal/tests/test_ccdbhg.py -q
