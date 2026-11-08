"""Multi-block RNS negacyclic NTT with exact 32-bit Shoup butterflies."""
import argparse
import hashlib
import json
import pathlib
import time
from datetime import datetime, timezone

import cupy as cp
import numpy as np
from experiments.rns_ntt import multiply_mod

SOURCE=r'''
typedef unsigned int U;typedef unsigned long long W;
__device__ U add(U a,U b,U p){U x=a+b;return x>=p?x-p:x;}
__device__ U sub(U a,U b,U p){return a>=b?a-b:a+p-b;}
__device__ U multiply(U a,U w,U quotient,U p,int shoup){
 if(!shoup)return (W)a*w%p;
 U q=__umulhi(a,quotient),r=a*w-q*p;return r>=p?r-p:r;
}
extern "C" __global__ void prepare(const U* a,U* x,const U* weights,const U* quotients,const U* rev,
 const U* primes,int n,int channels,int limbs,int shoup){
 int i=blockIdx.x*256+threadIdx.x;
 if(i<n*channels){int c=i/n,k=i%n,l=c%limbs,p=primes[l];
 x[c*n+rev[k]]=multiply(a[i],weights[l*n+k],quotients[l*n+k],p,shoup);}
}
extern "C" __global__ void stage(U* a,U* b,const U* roots,const U* quotients,const U* primes,
 int n,int channels,int limbs,int width,int pair,int shoup){
 int j=blockIdx.x*256+threadIdx.x;
 if(j<n/2*channels){int c=j/(n/2),k=j%(n/2),h=k%(width/2),i=c*n+k/(width/2)*width+h,l=c%limbs;
 U p=primes[l],w=roots[l*(n/2)+h*n/width],q=quotients[l*(n/2)+h*n/width];
 U x=a[i],y=multiply(a[i+width/2],w,q,p,shoup);a[i]=add(x,y,p);a[i+width/2]=sub(x,y,p);
 if(pair){x=b[i];y=multiply(b[i+width/2],w,q,p,shoup);b[i]=add(x,y,p);b[i+width/2]=sub(x,y,p);}}
}
extern "C" __global__ void tile(U* a,U* b,const U* roots,const U* quotients,const U* primes,
 int n,int limbs,int tile_n,int pair){
 extern __shared__ U mem[];U* x=mem;U* y=mem+tile_n;
 int c=blockIdx.y,start=blockIdx.x*tile_n,l=c%limbs,t=threadIdx.x;U p=primes[l];
 for(int i=t;i<tile_n;i+=256){x[i]=a[c*n+start+i];if(pair)y[i]=b[c*n+start+i];}__syncthreads();
 for(int width=2;width<=tile_n;width*=2){
  for(int j=t;j<tile_n/2;j+=256){int h=j%(width/2),i=j/(width/2)*width+h;
   U w=roots[l*(n/2)+h*n/width],q=quotients[l*(n/2)+h*n/width];
   U u=x[i],v=multiply(x[i+width/2],w,q,p,1);x[i]=add(u,v,p);x[i+width/2]=sub(u,v,p);
   if(pair){u=y[i];v=multiply(y[i+width/2],w,q,p,1);y[i]=add(u,v,p);y[i+width/2]=sub(u,v,p);}
  }__syncthreads();
 }
 for(int i=t;i<tile_n;i+=256){a[c*n+start+i]=x[i];if(pair)b[c*n+start+i]=y[i];}
}
extern "C" __global__ void product_reverse(const U* a,const U* b,U* out,const U* rev,const U* primes,
 int n,int channels,int limbs){
 int i=blockIdx.x*256+threadIdx.x;
 if(i<n*channels){int c=i/n,k=i%n;out[c*n+rev[k]]=(W)a[i]*b[i]%primes[c%limbs];}
}
extern "C" __global__ void finish(U* a,const U* weights,const U* quotients,const U* primes,
 int n,int channels,int limbs,int shoup){
 int i=blockIdx.x*256+threadIdx.x;
 if(i<n*channels){int l=i/n%limbs,k=i%n;a[i]=multiply(a[i],weights[l*n+k],quotients[l*n+k],primes[l],shoup);}
}
'''


def prime_test(n):
    if n<2:return False
    for p in (2,3,5,7,11):
        if n%p==0:return n==p
    d,s=n-1,0
    while d%2==0:d//=2;s+=1
    for base in (2,3,5,7,11):
        x=pow(base,d,n)
        if x in (1,n-1):continue
        for _ in range(s-1):
            x=x*x%n
            if x==n-1:break
        else:return False
    return True


def generator(p):
    factors=[];v=p-1;d=2
    while d*d<=v:
        if v%d==0:
            factors.append(d)
            while v%d==0:v//=d
        d+=1
    if v>1:factors.append(v)
    for g in range(2,p):
        if all(pow(g,(p-1)//factor,p)!=1 for factor in factors):return g
    raise AssertionError('No generator')


def basis():
    primes=[2013265921,1811939329]
    for k in range(((1<<31)-2)//131072,1,-1):
        p=k*131072+1
        if p not in primes and prime_test(p):primes.append(p)
        if len(primes)==16:break
    assert len(primes)==16 and all(prime_test(p) and p<1<<31 for p in primes)
    return [(p,generator(p)) for p in primes]


def make_plan(n,batch,selected):
    limbs=len(selected);channels=batch*limbs
    arrays=[[],[],[],[]]
    for p,g in selected:
        psi=pow(g,(p-1)//(2*n),p)
        assert pow(psi,n,p)==p-1
        arrays[0].append([pow(psi,i,p) for i in range(n)])
        arrays[1].append([pow(psi,-i,p)*pow(n,-1,p)%p for i in range(n)])
        arrays[2].append([pow(psi,2*i,p) for i in range(n//2)])
        arrays[3].append([pow(psi,-2*i,p) for i in range(n//2)])
    p=np.array([p for p,g in selected],np.uint64)[:,None]
    tables=[]
    for values in arrays:
        w=np.array(values,np.uint64)
        q=((w<<np.uint64(32))//p).astype(np.uint32)
        tables.append((cp.asarray(w.astype(np.uint32)),cp.asarray(q)))
    rev=cp.asarray(np.array([int(f'{i:0{n.bit_length()-1}b}'[::-1],2) for i in range(n)],np.uint32))
    return dict(n=n,batch=batch,limbs=limbs,channels=channels,tables=tables,rev=rev,
                primes=cp.asarray(p[:,0].astype(np.uint32)),
                buffers=[cp.empty((channels,n),cp.uint32) for _ in range(3)])


def compute(a,b,plan,kernels,mode):
    n,channels,limbs=(plan[x] for x in ('n','channels','limbs'))
    nn,cc,ll=(np.int32(x) for x in (n,channels,limbs))
    primes,rev=plan['primes'],plan['rev']
    twist,finish,forward,inverse=plan['tables']
    x,y,z=plan['buffers']
    shoup=np.int32(mode!='global_modulo');grid=((n*channels+255)//256,)
    for source,target in ((a,x),(b,y)):
        kernels['prepare'](grid,(256,),(source,target,*twist,rev,primes,nn,cc,ll,shoup))
    def transform(first,second,roots,pair):
        start=2
        if mode=='tiled_shoup':
            tile_n=1024
            kernels['tile']((n//tile_n,channels),(256,),
                (first,second,*roots,primes,nn,ll,np.int32(tile_n),np.int32(pair)),shared_mem=tile_n*4*(2 if pair else 1))
            start=tile_n*2
        width=start
        while width<=n:
            kernels['stage'](((n//2*channels+255)//256,),(256,),
                (first,second,*roots,primes,nn,cc,ll,np.int32(width),np.int32(pair),shoup))
            width*=2
    transform(x,y,forward,True)
    kernels['product_reverse'](grid,(256,),(x,y,z,rev,primes,nn,cc,ll))
    transform(z,z,inverse,False)
    kernels['finish'](grid,(256,),(z,*finish,primes,nn,cc,ll,shoup))
    return z


def main():
    assert __debug__
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,default=20261111)
    parser.add_argument('--output',default='results/large-ntt.json')
    args=parser.parse_args();rng=np.random.default_rng(args.seed)
    selected_basis=basis()
    module=cp.RawModule(code=SOURCE)
    kernels={name:module.get_function(name) for name in ('prepare','stage','tile','product_reverse','finish')}
    cases=[]
    profiles=[(n,limbs,1) for n in (16384,32768,65536) for limbs in (2,8,16)]
    profiles.extend((65536,limbs,8) for limbs in (2,8,16))
    for n,limbs,batch in profiles:
        selected=selected_basis[:limbs];plan=make_plan(n,batch,selected)
        a=np.empty((batch*limbs,n),np.uint32);b=np.empty_like(a)
        for c in range(batch*limbs):
            p=selected[c%limbs][0]
            a[c]=rng.integers(0,p,n,dtype=np.uint32)
            b[c]=rng.integers(0,p,n,dtype=np.uint32)
        # Full-residue inputs; zero and maximal magnitudes occupy separate RNS channels.
        if batch*limbs>=4:
            a[0].fill(0);a[1].fill(selected[1][0]-1);b[1].fill(selected[1][0]-1)
        da,db=cp.asarray(a),cp.asarray(b)
        expected=None;graphs={}
        for mode in ('global_modulo','global_shoup','tiled_shoup'):
            result=compute(da,db,plan,kernels,mode)
            host=cp.asnumpy(result)
            if expected is None:expected=host
            else:assert np.array_equal(host,expected),(n,limbs,batch,mode)
            capture=cp.cuda.Stream(non_blocking=True)
            cp.cuda.get_current_stream().synchronize()
            with capture:
                capture.begin_capture();compute(da,db,plan,kernels,mode);graphs[mode]=capture.end_capture()
            graphs[mode].launch()
            assert np.array_equal(cp.asnumpy(result),expected)
        oracle_channels=sorted(set([0,1,batch*limbs-1]))
        for c in oracle_channels:
            p,g=selected[c%limbs]
            assert expected[c].tolist()==multiply_mod(a[c].tolist(),b[c].tolist(),p,g),(n,c)
        samples={mode:{'resident_wall_ms':[],'device_elapsed_ms':[],'transfer_wall_ms':[]} for mode in graphs}
        output=plan['buffers'][2]
        for iteration in range(35):
            modes=list(graphs)
            if iteration%2:modes.reverse()
            for mode in modes:
                begin,end=cp.cuda.Event(),cp.cuda.Event()
                start=time.perf_counter();begin.record();graphs[mode].launch();end.record();end.synchronize()
                wall=(time.perf_counter()-start)*1000;device=cp.cuda.get_elapsed_time(begin,end)
                start=time.perf_counter();da.set(a);db.set(b);graphs[mode].launch();actual=cp.asnumpy(output)
                full=(time.perf_counter()-start)*1000
                assert np.array_equal(actual,expected)
                if iteration>=5:
                    for key,value in (('resident_wall_ms',wall),('device_elapsed_ms',device),('transfer_wall_ms',full)):
                        samples[mode][key].append(value)
        cases.append(dict(n=n,limbs=limbs,batch=batch,oracle_channels=oracle_channels,
                          all_residues_equal=True,samples=samples,
                          memory_pool_reserved_bytes=cp.get_default_memory_pool().total_bytes()))
        print(n,limbs,batch,{k:float(np.median(v['resident_wall_ms'])) for k,v in samples.items()},flush=True)
    record=dict(utc=datetime.now(timezone.utc).isoformat(),seed=args.seed,warmups=5,samples=30,
                basis=selected_basis,device=cp.cuda.runtime.getDeviceProperties(0)['name'].decode(),
                source_sha256={p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in
                               ('large_ntt_study.py','experiments/rns_ntt.py')},cases=cases,
                scope='Exact negacyclic RNS products with independent full-range 31-bit residues. No target-q CRT, ciphertext security claim, rescaling, keys, or bootstrapping. All timed variants use CUDA Graphs. Plan, twiddle generation and capture excluded. Transfer path includes two H2D and one D2H RNS tensor.')
    pathlib.Path(args.output).write_text(json.dumps(record,indent=2)+'\n')


if __name__=='__main__':main()
