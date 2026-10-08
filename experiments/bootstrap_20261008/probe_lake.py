"""Read-only lake schema and compute probe. Prints metadata, never record values."""
import argparse
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/opt/openalex'))
    args = parser.parse_args()
    if not args.root.is_dir():
        raise SystemExit('Lake path unavailable: ' + str(args.root))
    report = {'root': str(args.root), 'platform': platform.platform(),
              'machine': platform.machine(), 'python': platform.python_version(),
              'modules': {m: bool(importlib.util.find_spec(m)) for m in
                          ['pyarrow', 'duckdb', 'torch', 'transformers', 'sentence_transformers']},
              'tables': {}, 'limitations': ['metadata-only; no corpus quality/coverage inference',
                                           'sampled schemas may differ in unsampled files']}
    for table in sorted(args.root.iterdir()):
        if not table.is_dir():
            continue
        files = sorted(table.rglob('*.parquet'))
        if not files:
            continue
        item = {'files': len(files), 'bytes': sum(p.stat().st_size for p in files),
                'partition_labels': sorted({str(p.parent.relative_to(table)) for p in files}),
                'schema_samples': []}
        if report['modules']['pyarrow']:
            import pyarrow.parquet as pq
            # Spread metadata samples across file order; no paper values read.
            for i in sorted({0, len(files)//2, len(files)-1}):
                path = files[i]
                try:
                    p = pq.ParquetFile(path)
                    item['schema_samples'].append({'file': str(path.relative_to(table)),
                                                   'rows': p.metadata.num_rows,
                                                   'row_groups': p.metadata.num_row_groups,
                                                   'schema': str(p.schema_arrow)})
                except Exception as exc:
                    item['schema_samples'].append({'file': str(path), 'error': str(exc)})
        report['tables'][table.name] = item
    if shutil.which('nvidia-smi'):
        result = subprocess.run(['nvidia-smi', '--query-gpu=name,driver_version,memory.total,memory.used',
                                 '--format=csv,noheader'], capture_output=True, text=True, timeout=15)
        report['gpu'] = {'exit_code': result.returncode, 'summary': result.stdout.strip(),
                         'error': result.stderr.strip()}
    else:
        report['gpu'] = {'status': 'nvidia-smi unavailable'}
    if report['modules']['torch']:
        try:
            import torch
            report['torch'] = {'version': torch.__version__, 'cuda_runtime': torch.version.cuda,
                               'cuda_available': torch.cuda.is_available()}
        except Exception as exc:
            report['torch'] = {'error': str(exc)}
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
