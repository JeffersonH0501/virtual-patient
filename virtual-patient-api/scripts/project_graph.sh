#!/usr/bin/env bash
set -euo pipefail
cd /workspace
if [[ "${1:-}" != prepare && "${1:-}" != build ]]; then
  exec graphify "$@"
fi
python - "$1" <<'PY'
import json
import sys
from pathlib import Path

root = Path('/workspace')
out = root / 'graphify-out'
out.mkdir(exist_ok=True)

def write(name, value):
    (out / name).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')

if sys.argv[1] == 'prepare':
    from graphify.detect import detect
    from graphify.extract import extract
    detection = detect(root, cache_root=root)
    # LaTeX and BibTeX are semantic inputs even when a detector version leaves them unclassified.
    documents = set(detection['files'].get('document', []))
    documents.update(str(p) for p in (root / 'DocumentoOverleaf').rglob('*')
                     if p.suffix in {'.tex', '.bib'} and 'respaldo' not in p.name.lower())
    detection['files']['document'] = sorted(documents)
    # Preserve CSS and container/configuration contracts unsupported by the AST parser.
    extra_documents = sorted(p for p in detection.get('unclassified', [])
                             if Path(p).suffix in {'.css', '.ini', '.conf'} or Path(p).name == 'Dockerfile')
    detection['files']['document'].extend(extra_documents)
    detection['total_files'] = len({p for files in detection['files'].values() for p in files})
    write('.graphify_detect.json', detection)
    (out / '.graphify_root').write_text(str(root), encoding='utf-8')
    (out / '.graphify_python').write_text(sys.executable, encoding='utf-8')
    batches, batch, lines = [], [], 0
    for source in sorted(documents):
        count = len(Path(source).read_text(encoding='utf-8', errors='replace').splitlines())
        if batch and (len(batch) >= 22 or lines + count > 6000):
            batches.append(batch)
            batch, lines = [], 0
        batch.append(source)
        lines += count
    if batch:
        batches.append(batch)
    if extra_documents:
        batches.append(extra_documents)
    write('.graphify_batches.json', batches)
    files = [Path(p) for p in detection['files'].get('code', [])]
    result = extract(files, root=root, cache_root=root, max_workers=2)
    write('.graphify_ast.json', result)
    print(json.dumps({'code_files': len(files), 'document_files': len(documents),
                      'batches': batches, 'nodes': len(result['nodes']), 'edges': len(result['edges'])}))
else:
    from graphify.build import build_from_json
    from graphify.cluster import cluster, score_all
    from graphify.analyze import god_nodes, surprising_connections, suggest_questions
    from graphify.report import generate
    from graphify.export import to_json, to_html
    from graphify.diagnostics import diagnose_extraction, format_diagnostic_report
    from graphify.detect import save_manifest
    from graphify.cli import _stamped_manifest_files
    extraction = json.loads((out / '.graphify_ast.json').read_text())
    batches = json.loads((out / '.graphify_batches.json').read_text())
    expected = {p for batch in batches for p in batch}
    covered = set()
    for index, batch in enumerate(batches, 1):
        chunk = json.loads((out / f'.graphify_chunk_{index:02}.json').read_text(encoding='utf-8'))
        assert isinstance(chunk['nodes'], list) and isinstance(chunk['edges'], list)
        for source in batch:
            count = len(Path(source).read_text(encoding='utf-8', errors='replace').splitlines())
            assert chunk.get('coverage', {}).get(source) == count, f'Incomplete coverage: {source}'
            covered.add(source)
        for item in chunk['nodes'] + chunk['edges']:
            assert item['source_file'] in batch, f'Unexpected semantic source: {item}'
            item['_origin'] = 'semantic'
        extraction['nodes'].extend(chunk['nodes'])
        extraction['edges'].extend(chunk['edges'])
        extraction.setdefault('hyperedges', []).extend(chunk.get('hyperedges', []))
    assert covered == expected
    write('.graphify_extract.json', extraction)
    health = diagnose_extraction(extraction, directed=True, root=str(root))
    write('GRAPH_HEALTH.json', health)
    print(format_diagnostic_report(health))
    graph = build_from_json(extraction, root=str(root), directed=True)
    assert graph.number_of_nodes(), 'Empty graph'
    communities = cluster(graph)
    # Use the most connected member as a reproducible community label.
    labels = {cid: graph.nodes[max(nodes, key=lambda n: graph.degree(n))].get('label', str(cid))
              for cid, nodes in communities.items()}
    assert to_json(graph, communities, str(out / 'graph.json'), community_labels=labels), 'Export refused'
    detection = json.loads((out / '.graphify_detect.json').read_text())
    report = generate(graph, communities, score_all(graph, communities), labels,
                      god_nodes(graph), surprising_connections(graph, communities), detection,
                      {'input': 0, 'output': 0}, str(root),
                      suggested_questions=suggest_questions(graph, communities, labels))
    (out / 'GRAPH_REPORT.md').write_text(report, encoding='utf-8')
    assert to_html(graph, communities, str(out / 'graph.html'), community_labels=labels)
    corpus = detection['files']
    save_manifest(_stamped_manifest_files(corpus, extraction, root), root=str(root),
                  scan_corpus={p for files in corpus.values() for p in files})
    print(f'Graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges; {len(communities)} communities')
PY
