#!/usr/bin/env bash
# Public advisory lookups disclose only package names/versions, no credentials.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
docker compose -f docker-compose.local.yml run --rm --no-deps -T ui node --input-type=module <<'JS'
import {spawnSync} from 'node:child_process';
const result = spawnSync('yarn', ['npm', 'audit', '--all', '--recursive', '--json'], {encoding: 'utf8', maxBuffer: 20 * 1024 * 1024});
const advisories = result.stdout.split('\n').filter(Boolean).map(line => JSON.parse(line))
  .filter(item => item.children?.URL)
  .map(item => ({package: item.value, severity: item.children.Severity,
                versions: item.children['Tree Versions'], url: item.children.URL}));
const counts = {};
for (const item of advisories) counts[item.severity] = (counts[item.severity] || 0) + 1;
console.log(JSON.stringify({source: 'yarn npm audit', exitCode: result.status, advisoryEntries: advisories.length,
  severityCounts: counts, advisories}));
if (!advisories.length && result.status) throw new Error('Advisory lookup failed');
JS

docker compose -f docker-compose.local.yml run --rm --no-deps -T api python - <<'PY'
import importlib.metadata
import json
import urllib.request
packages = sorted({(item.metadata['Name'], item.version) for item in importlib.metadata.distributions() if item.metadata['Name']})
query = {'queries': [{'package': {'name': name, 'ecosystem': 'PyPI'}, 'version': version} for name, version in packages]}
request = urllib.request.Request('https://api.osv.dev/v1/querybatch', data=json.dumps(query).encode(), headers={'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(request, timeout=40) as response:
        results = json.load(response)['results']
    affected = [{'package': name, 'version': version, 'advisoryIds': [v['id'] for v in result.get('vulns', [])]}
                for (name, version), result in zip(packages, results) if result.get('vulns')]
    print(json.dumps({'source': 'OSV PyPI querybatch', 'installedPackagesChecked': len(packages), 'affected': affected}))
except Exception as error:
    print(json.dumps({'source': 'OSV PyPI querybatch', 'status': 'lookup_failed', 'errorType': type(error).__name__}))
PY
