"""Isolated native 64-bit square optimization in actual CKKS/bootstrap paths."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess

REVISION='837ffc87aa263bdfebfdfd1d077e5a52c7ae1ed1'

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    assert __debug__
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('upstream',type=Path);parser.add_argument('build',type=Path)
    parser.add_argument('--ninja',default='ninja');args=parser.parse_args()
    upstream,old=args.upstream.resolve(),args.build.resolve();new=Path('build/square-integration').resolve();new.mkdir(parents=True,exist_ok=True)
    def run(command,cwd=None):return subprocess.check_output(command,cwd=cwd,text=True)
    assert run(['git','-C',str(upstream),'rev-parse','HEAD']).strip()==REVISION
    assert not run(['git','-C',str(upstream),'status','--porcelain']).strip()
    source=upstream/'src/lib/kernel/multiplication.cu';original=source.read_text(encoding='utf-8-sig')
    needle='Data64 out_1_1 = OPERATOR_GPU_64::mult(ct0_1, ct1_0, modulus[idy]);'
    assert original.count(needle)==1
    # Apply the published attributed patch to an isolated source tree only.
    isolated=new/'source';target=isolated/'src/lib/kernel/multiplication.cu';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(original)
    patch=str(Path('patches/square-alias.patch').resolve())
    run(['patch','--dry-run','-p1','-i',patch],cwd=isolated)
    run(['patch','-p1','-i',patch],cwd=isolated)
    assert target.read_text()!=original and 'in1 == in2 ? out_1_0' in target.read_text()
    all_commands={}
    for name in ('ckks','bootstrap'):
        all_commands[name]=run([args.ninja,'-t','commands',f'requant_{name}_study'],cwd=old).splitlines()
    compile_commands=[s for s in all_commands['ckks'] if ' -c '+str(source)+' ' in s];assert len(compile_commands)==1
    command=shlex.split(compile_commands[0]);patched=command.copy();obj=new/'multiplication.cu.o'
    for flag in ('-o','-MF','-MT'):
        i=patched.index(flag)+1;patched[i]=str(obj)+('.d' if flag=='-MF' else '')
    patched[patched.index(str(source))]=str(target)
    run(patched,cwd=old)
    archive=new/'libheongpu.a';shutil.copyfile(old/'src/libheongpu.a',archive)
    run(['ar','r',str(archive),str(obj)]);run(['ranlib',str(archive)])
    binaries={};harnesses={}
    for name,lines in all_commands.items():
        output=f'requant_{name}_study';device=f'CMakeFiles/{output}.dir/cmake_device_link.o'
        dlinks=[s for s in lines if ' -dlink ' in s and ' -o '+device+' ' in s];assert len(dlinks)==1
        links=[s for s in lines if ' -o '+output+' ' in s and ' -dlink ' not in s];assert len(links)==1
        original_source=Path('native')/f'{name}_study.cpp';harness_source=new/f'{name}-harness.cpp'
        text=original_source.read_text();assert text.count('pool.max_host_fraction=.10f;')==1
        harness_source.write_text(text.replace('pool.max_host_fraction=.10f;','pool.max_host_bytes=256ULL<<20;'))
        compiles=[s for s in lines if ' -c ' in s and str(original_source) in s];assert len(compiles)==1
        hc=shlex.split(compiles[0]);source_index=hc.index('-c')+1;hc[source_index]=str(harness_source)
        for flag in ('-o','-MF','-MT'):
            i=hc.index(flag)+1;hc[i]=str(new/f'{name}-harness.o')+('.d' if flag=='-MF' else '')
        run(hc,cwd=old);harnesses[name]=dict(generated_source_sha256=digest(harness_source),max_host_pool_bytes=256<<20)
        pair=[]
        for variant,library in (('baseline',old/'src/libheongpu.a'),('square_alias',archive)):
            dl=shlex.split(dlinks[0]);host=next(v for v in dl if v.startswith(f'CMakeFiles/{output}.dir/') and v.endswith('.cpp.o'))
            dl[dl.index(host)]=str(new/f'{name}-harness.o');dl[dl.index('src/libheongpu.a')]=str(library)
            dl[dl.index('-o')+1]=str(new/f'{name}-{variant}-device.o');run(dl,cwd=old)
            assert links[0].startswith(': && ') and links[0].endswith(' && :')
            link=shlex.split(links[0][5:-5]);link[link.index('src/libheongpu.a')]=str(library)
            link[link.index(host)]=str(new/f'{name}-harness.o');link[link.index(device)]=str(new/f'{name}-{variant}-device.o')
            binary=new/f'requant_{name}_{variant}';link[link.index('-o')+1]=str(binary)
            dep=[v for v in link if v.startswith('-Wl,--dependency-file=')];assert len(dep)==1;link.remove(dep[0])
            run(link,cwd=old);pair.append(binary)
        binaries[name]=pair
    unit=command.copy();unit[unit.index(str(source))]=str(Path('native/square_check.cu').resolve())
    for flag in ('-o','-MF','-MT'):
        i=unit.index(flag)+1;unit[i]=str(new/'square-check.o')+('.d' if flag=='-MF' else '')
    run(unit,cwd=old)
    # Link the independent CPU-integer oracle against the actual patched archive.
    lines=all_commands['ckks'];dl=shlex.split(next(s for s in lines if ' -dlink ' in s and ' -o CMakeFiles/requant_ckks_study.dir/cmake_device_link.o ' in s))
    host=next(v for v in dl if v.startswith('CMakeFiles/requant_ckks_study.dir/') and v.endswith('.cpp.o'))
    dl[dl.index(host)]=str(new/'square-check.o');dl[dl.index('src/libheongpu.a')]=str(archive);dl[dl.index('-o')+1]=str(new/'check-device.o');run(dl,cwd=old)
    link=shlex.split(next(s for s in lines if ' -o requant_ckks_study ' in s and ' -dlink ' not in s)[5:-5])
    link[link.index(host)]=str(new/'square-check.o');link[link.index('CMakeFiles/requant_ckks_study.dir/cmake_device_link.o')]=str(new/'check-device.o')
    link[link.index('src/libheongpu.a')]=str(archive);link[link.index('-o')+1]=str(new/'square-check')
    link=[v for v in link if not v.startswith('-Wl,--dependency-file=')];run(link,cwd=old)
    qualification=json.loads(run([str(new/'square-check')]))
    record=dict(harnesses=harnesses,utc=datetime.now(timezone.utc).isoformat(),revision=REVISION,coefficient_qualification=qualification,cases=[],
                source_sha256={p:digest(p) for p in ('integration_study.py','native/square_check.cu','native/ckks_study.cpp','native/bootstrap_study.cpp','patches/square-alias.patch')},
                upstream_kernel_sha256=digest(source),patched_kernel_sha256=digest(target),
                archive_sha256={'baseline':digest(old/'src/libheongpu.a'),'square_alias':digest(archive)},
                binary_sha256={name:{'baseline':digest(pair[0]),'square_alias':digest(pair[1])} for name,pair in binaries.items()},
                scope='Same pinned64-bit/RNS library, security parameters and full-slot decrypt checks. Native harnesses differ only in a fixed256MiB max host-pool budget for both baselines/variants; original64/128MiB initial budgets retained. All native allocation validation remains.  One isolated kernel object replaced, device link rebuilt without linker overrides. Alias path reuses an equal cross product; general multiplication unchanged. Timings are complete sequential native harness runs (5 warmups/30 samples), order reversed across two seeds, not within-iteration paired. No 31-bit substitution or production security claim.')
    for seed in (20261112,20261212):
        for name,n in (('ckks',8192),('ckks',16384),('bootstrap',0)):
            variants=['baseline','square_alias']
            if seed==20261212:variants.reverse()
            for variant in variants:
                executable=binaries[name][variant=='square_alias'];path=new/f'{name}-{n}-{seed}-{variant}.json'
                call=[str(executable)]+([str(n)] if n else [])+[str(seed),str(path)]
                print(name,n,seed,variant,flush=True);subprocess.run(call,check=True,timeout=900)
                value=json.loads(path.read_text());record['cases'].append(dict(application=name,n=n,seed=seed,variant=variant,result=value))
                Path('results/integration-study.json').write_text(json.dumps(record,indent=2)+'\n')
    assert digest(source)==record['upstream_kernel_sha256']
    assert digest(old/'src/libheongpu.a')==record['archive_sha256']['baseline']

if __name__=='__main__':main()
