"""Two-prime negacyclic NTT: global stages versus one shared-memory block."""
import hashlib
import argparse
import json
import pathlib
import re
import time
from datetime import datetime, timezone

import cupy as cp
import numpy as np
from experiments.rns_ntt import PRIMES, Q, multiply_mod, schoolbook

SOURCE = r'''
typedef unsigned int U; typedef unsigned long long W;
__device__ U mul(U a,U b,U p){return (W)a*b%p;}
extern "C" __global__ void prepare(const U* a,U* z,const U* twist,const U* rev,int n,int batch,U p){
 int i=blockIdx.x*256+threadIdx.x;
 if(i<n*batch)z[i/n*n+rev[i%n]]=mul(a[i],twist[i%n],p);
}
extern "C" __global__ void stage(U* z,const U* roots,int n,int batch,int width,U p){
 int i=blockIdx.x*256+threadIdx.x;
 if(i<n/2*batch){int row=i/(n/2),j=i%(n/2),k=j%(width/2),x=row*n+j/(width/2)*width+k;
 U a=z[x],b=mul(z[x+width/2],roots[k*n/width],p);
 z[x]=(a+(W)b)%p;z[x+width/2]=(a+(W)p-b)%p;}
}
extern "C" __global__ void product_reverse(const U* a,const U* b,U* z,const U* rev,int n,int batch,U p){
 int i=blockIdx.x*256+threadIdx.x;if(i<n*batch)z[i/n*n+rev[i%n]]=mul(a[i],b[i],p);
}
extern "C" __global__ void finish(U* z,const U* untwist,int n,int batch,U p,U invn){
 int i=blockIdx.x*256+threadIdx.x;if(i<n*batch)z[i]=mul(mul(z[i],invn,p),untwist[i%n],p);
}
extern "C" __global__ void shared_product(const U* a,const U* b,U* out,const U* twist,const U* untwist,
 const U* roots,const U* inverse,const U* rev,int n,U p,U invn){
 extern __shared__ U mem[]; U* x=mem;U* y=mem+n;U* z=mem+2*n;
 int row=blockIdx.x, t=threadIdx.x;
 for(int i=t;i<n;i+=blockDim.x){x[rev[i]]=mul(a[row*n+i],twist[i],p);y[rev[i]]=mul(b[row*n+i],twist[i],p);}
 __syncthreads();
 for(int w=2;w<=n;w*=2){
   for(int j=t;j<n/2;j+=blockDim.x){int k=j%(w/2),i=j/(w/2)*w+k;U r=roots[k*n/w];
     U ax=x[i],bx=mul(x[i+w/2],r,p),ay=y[i],by=mul(y[i+w/2],r,p);
     x[i]=(ax+(W)bx)%p;x[i+w/2]=(ax+(W)p-bx)%p;y[i]=(ay+(W)by)%p;y[i+w/2]=(ay+(W)p-by)%p;
   }__syncthreads();
 }
 for(int i=t;i<n;i+=blockDim.x)z[rev[i]]=mul(x[i],y[i],p);
 __syncthreads();
 for(int w=2;w<=n;w*=2){
   for(int j=t;j<n/2;j+=blockDim.x){int k=j%(w/2),i=j/(w/2)*w+k;U a=z[i],b=mul(z[i+w/2],inverse[k*n/w],p);
     z[i]=(a+(W)b)%p;z[i+w/2]=(a+(W)p-b)%p;
   }__syncthreads();
 }
 for(int i=t;i<n;i+=blockDim.x)out[row*n+i]=mul(mul(z[i],invn,p),untwist[i],p);
}
extern "C" __global__ void gpu_crt(const U* a,const U* b,U* out,int count,U inv){
 int i=blockIdx.x*256+threadIdx.x;
 if(i<count){const W p0=2013265921ULL,p1=1811939329ULL,mod=p0*p1;
 W t=(((b[i]+p1-a[i]%p1)%p1)*inv)%p1;
 W x=a[i]+p0*t;
 out[i]=x>mod/2 ? (x%65537+65537-mod%65537)%65537 : x%65537;}
}
'''
module = cp.RawModule(code=SOURCE)
kernels = {name: module.get_function(name) for name in
           ('prepare', 'stage', 'product_reverse', 'finish', 'shared_product','gpu_crt')}
specialized = {}
for prime, _ in PRIMES:
    source = '#define MODULUS '+str(prime)+'U\n'+re.sub(r'%p\b','%MODULUS',SOURCE)
    specialized_module=cp.RawModule(code=source)
    specialized[prime]={name:specialized_module.get_function(name) for name in kernels}


def plan(n, batch):
    rev = np.array([int(f'{i:0{n.bit_length()-1}b}'[::-1], 2) for i in range(n)], np.uint32)
    plans = []
    for p, g in PRIMES:
        psi = pow(g, (p - 1) // (2*n), p)
        assert pow(psi, n, p) == p - 1
        arrays = [[pow(psi, i, p) for i in range(n)], [pow(psi, -i, p) for i in range(n)],
                  [pow(psi, 2*i, p) for i in range(n//2)], [pow(psi, -2*i, p) for i in range(n//2)]]
        plans.append((np.uint32(p), np.uint32(pow(n, -1, p)),
                      *[cp.asarray(x, dtype=cp.uint32) for x in arrays], cp.asarray(rev),
                      *[cp.empty((batch, n), cp.uint32) for _ in range(3)]))
    return plans


def compute(a, b, plans, shared, constant_prime=False):
    batch, n = a.shape
    nn, bb = np.int32(n), np.int32(batch)
    grid = ((n*batch+255)//256,)
    outputs = []
    for p, invn, twist, untwist, roots, inverse, rev, x, y, z in plans:
        active=specialized[int(p)] if constant_prime else kernels
        if shared:
            active['shared_product']((batch,), (256,),
                (a, b, z, twist, untwist, roots, inverse, rev, nn, p, invn), shared_mem=12*n)
        else:
            for source, target in ((a, x), (b, y)):
                kernels['prepare'](grid, (256,), (source, target, twist, rev, nn, bb, p))
                for width in (2**k for k in range(1, n.bit_length())):
                    kernels['stage'](((n*batch//2+255)//256,), (256,), (target, roots, nn, bb, np.int32(width), p))
            kernels['product_reverse'](grid, (256,), (x, y, z, rev, nn, bb, p))
            for width in (2**k for k in range(1, n.bit_length())):
                kernels['stage'](((n*batch//2+255)//256,), (256,), (z, inverse, nn, bb, np.int32(width), p))
            kernels['finish'](grid, (256,), (z, untwist, nn, bb, p, invn))
        outputs.append(z)
    return outputs


def crt(residues):
    p0, p1 = (x[0] for x in PRIMES)
    a, b = (cp.asnumpy(x).astype(np.int64) for x in residues)
    value = a + p0 * (((b-a) * pow(p0, -1, p1)) % p1)
    value = np.where(value > p0*p1//2, value-p0*p1, value)
    return value % Q


def device_crt(residues, out):
    count=out.size
    kernels['gpu_crt'](((count+255)//256,),(256,),
        (*residues,out,np.int32(count),np.uint32(pow(PRIMES[0][0],-1,PRIMES[1][0]))))
    return out


def main():
    assert __debug__
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,default=20261109)
    parser.add_argument('--output',default='results/gpu-study.json')
    args=parser.parse_args()
    rng = np.random.default_rng(args.seed)
    cases = []
    for n in (256, 1024, 2048):
        assert 2*n*(Q-1)**2 < PRIMES[0][0]*PRIMES[1][0]
        for batch in (1, 16, 128):
            a = rng.integers(0, Q, (batch, n), dtype=np.uint32)
            b = rng.integers(0, Q, (batch, n), dtype=np.uint32)
            # Larger batches include exact zero and worst-magnitude boundary cases.
            if batch > 1:
                a[0].fill(0)
                a[1].fill(Q-1)
                b[1].fill(Q-1)
            plans = plan(n, batch)
            da, db = cp.asarray(a), cp.asarray(b)
            crt_output=cp.empty((batch,n),cp.uint32)
            expected = None
            oracle_rows = sorted(set((0, min(1,batch-1), batch-1)))
            for shared,constant in ((False,False),(True,False),(True,True)):
                residues = compute(da, db, plans, shared,constant)
                host = [cp.asnumpy(x) for x in residues]
                if expected is None:
                    expected = host
                else:
                    assert all(np.array_equal(x,y) for x,y in zip(expected,host))
                for row in oracle_rows:
                    for (p,g), actual in zip(PRIMES,host):
                        assert actual[row].tolist() == multiply_mod(a[row].tolist(), b[row].tolist(), p, g)
                final = crt(residues)
                assert np.array_equal(cp.asnumpy(device_crt(residues,crt_output)),final)
                if n == 256:
                    for row in oracle_rows:
                        assert final[row].tolist() == schoolbook(a[row].tolist(), b[row].tolist())
            samples = {mode: {'resident_wall_ms': [], 'device_elapsed_ms': [], 'transfer_crt_wall_ms': []}
                       for mode in ('global', 'shared','shared_gpu_crt','specialized_gpu_crt','global_graph_gpu_crt','specialized_graph_gpu_crt')}
            graphs={}
            cp.cuda.get_current_stream().synchronize()
            capture=cp.cuda.Stream(non_blocking=True)
            for mode in ('global_graph_gpu_crt','specialized_graph_gpu_crt'):
                with capture:
                    capture.begin_capture()
                    residues=compute(da,db,plans,mode.startswith('specialized'),mode.startswith('specialized'))
                    device_crt(residues,crt_output)
                    graphs[mode]=capture.end_capture()
                graphs[mode].launch()
                assert np.array_equal(cp.asnumpy(crt_output),final)
            for iteration in range(35):
                modes=list(samples)
                if iteration%2:modes.reverse()
                for mode in modes:
                    start_event, end_event = cp.cuda.Event(), cp.cuda.Event()
                    start = time.perf_counter()
                    start_event.record()
                    if mode in graphs:
                        graphs[mode].launch()
                    else:
                        result = compute(da, db, plans, mode!='global',mode=='specialized_gpu_crt')
                        if mode.endswith('gpu_crt'):device_crt(result,crt_output)
                    end_event.record()
                    end_event.synchronize()
                    wall = (time.perf_counter()-start)*1000
                    elapsed = cp.cuda.get_elapsed_time(start_event,end_event)
                    start = time.perf_counter()
                    da.set(a);db.set(b)
                    if mode in graphs:
                        graphs[mode].launch()
                        full_result=cp.asnumpy(crt_output)
                    else:
                        residues=compute(da, db, plans, mode!='global',mode=='specialized_gpu_crt')
                        full_result = cp.asnumpy(device_crt(residues,crt_output)) if mode.endswith('gpu_crt') else crt(residues)
                    full = (time.perf_counter()-start)*1000
                    assert np.array_equal(full_result, final)
                    if iteration>=5:
                        for key,value in (('resident_wall_ms',wall),('device_elapsed_ms',elapsed),('transfer_crt_wall_ms',full)):
                            samples[mode][key].append(value)
            cases.append(dict(n=n,batch=batch,oracle_rows=oracle_rows,all_variant_residues_equal=True,samples=samples))
            print(n,batch,{k:round(float(np.median(v['transfer_crt_wall_ms'])),3) for k,v in samples.items()},flush=True)
    output = dict(utc=datetime.now(timezone.utc).isoformat(), seed=args.seed,
                  source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                                 (pathlib.Path('gpu_study.py'),pathlib.Path('experiments/rns_ntt.py'))},
                  device=cp.cuda.runtime.getDeviceProperties(0)['name'].decode(), runtime=cp.cuda.runtime.runtimeGetVersion(),
                  driver=cp.cuda.runtime.driverGetVersion(),numpy=np.__version__,cupy=cp.__version__,
                  scope='Two-prime negacyclic product. Plans/twiddles precomputed. Full path includes H2D, GPU multiplication, D2H and CPU centered CRT mod 65537. No encryption or bootstrapping.',
                  warmups=5,samples=30,cases=cases)
    pathlib.Path(args.output).write_text(json.dumps(output,indent=2)+'\n')


if __name__ == '__main__':
    main()
