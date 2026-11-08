"""Record the pinned upstream build and bind executed harnesses to raw results."""
import argparse
import hashlib
import json
import pathlib
import subprocess
from datetime import datetime, timezone

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('upstream',type=pathlib.Path)
parser.add_argument('build',type=pathlib.Path)
args=parser.parse_args()
def command(*values):return subprocess.check_output(values,text=True).strip()
def digest(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
revision=command('git','-C',str(args.upstream),'rev-parse','HEAD')
assert revision=='837ffc87aa263bdfebfdfd1d077e5a52c7ae1ed1'
assert not command('git','-C',str(args.upstream),'status','--porcelain')
sources=['native/ckks_study.cpp','native/bootstrap_study.cpp','native/attach_heongpu.cmake','collect_heongpu_build.py']
results=sorted(pathlib.Path('results').glob('ckks-*.json'))+sorted(pathlib.Path('results').glob('bootstrap*.json'))
assert len(results)==6
cache=(args.build/'CMakeCache.txt').read_text()
settings=[line for line in cache.splitlines() if line.startswith(('CMAKE_BUILD_TYPE:','CMAKE_CUDA_ARCHITECTURES:','HEonGPU_VERSION:','RMM_VERSION:','CCCL_VERSION:'))]
dependency_revisions={}
for directory in sorted((args.build/'_deps').glob('*-src')):
    if (directory/'.git').exists():
        dependency_revisions[directory.name]=command('git','-C',str(directory),'rev-parse','HEAD')
record=dict(utc=datetime.now(timezone.utc).isoformat(),revision=revision,upstream_clean=True,
    submodules=command('git','-C',str(args.upstream),'submodule','status','--recursive').splitlines(),
    nvcc=command('/usr/local/cuda-13.3/bin/nvcc','--version'),gxx=command('g++','-dumpfullversion','-dumpversion'),
    cmake=command('cmake','--version').splitlines()[0],settings=settings,
    source_sha256={p:digest(p) for p in sources},result_sha256={p.name:digest(p) for p in results},
    binary_sha256={name:digest(args.build/name) for name in ('requant_ckks_study','requant_bootstrap_study')},
    dependencies={'RMM':'26.08.00','CCCL':json.loads((args.build/'_deps/cccl-src/cccl-version.json').read_text())['full'],'OpenSSL':'3.0.13','GMP':'6.3.0','NTL':'11.5.1','GF2X':'1.3.0'},dependency_source_revisions=dependency_revisions,
    scope='Post-run provenance for executed unmodified-library API harnesses. Native executable hashes are informational: rebuilds need not be byte-identical. Library sec128 is not an independent security audit.')
pathlib.Path('results/heongpu-build.json').write_text(json.dumps(record,indent=2)+'\n')
