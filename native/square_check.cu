// Exact coefficient qualification of both paths of the experimental library.
#include <heongpu/kernel/multiplication.cuh>
#include <vector>
#include <random>
#include <iostream>
#include <stdexcept>
static void check(cudaError_t e){if(e!=cudaSuccess)throw std::runtime_error(cudaGetErrorString(e));}
int main(){
    constexpr int n=8192;
    std::mt19937_64 rng(20261112);size_t checked=0;
    for(Data64 p:{Data64(2013265921),Data64(1125899906826241),Data64(1152921504606830593)}){
        Modulus64 mod(p),*dm;Data64 *a,*b,*out;
        check(cudaMalloc(&a,2*n*sizeof(Data64)));check(cudaMalloc(&b,2*n*sizeof(Data64)));
        check(cudaMalloc(&out,3*n*sizeof(Data64)));check(cudaMalloc(&dm,sizeof(mod)));
        check(cudaMemcpy(dm,&mod,sizeof(mod),cudaMemcpyHostToDevice));
        std::vector<Data64> x(2*n),y(2*n),z(3*n);
        for(int i=0;i<2*n;i++){x[i]=rng()%p;y[i]=rng()%p;}
        for(int i=0;i<4;i++){x[i]=i%2?p-1:0;y[i]=i<2?0:p-1;x[i+n]=p-1;y[i+n]=p-1;}
        check(cudaMemcpy(a,x.data(),x.size()*8,cudaMemcpyHostToDevice));
        check(cudaMemcpy(b,y.data(),y.size()*8,cudaMemcpyHostToDevice));
        for(bool alias:{false,true}){
            heongpu::cross_multiplication<<<n/256,256>>>(a,alias?a:b,out,dm,13,1);
            check(cudaGetLastError());check(cudaDeviceSynchronize());
            check(cudaMemcpy(z.data(),out,z.size()*8,cudaMemcpyDeviceToHost));
            const auto& rhs=alias?x:y;
            for(int i=0;i<n;i++){
                auto mul=[&](Data64 q,Data64 r){return Data64((__uint128_t(q)*r)%p);};
                Data64 expected[3]={mul(x[i],rhs[i]),Data64((__uint128_t(mul(x[i],rhs[i+n]))+mul(x[i+n],rhs[i]))%p),mul(x[i+n],rhs[i+n])};
                for(int j=0;j<3;j++){if(z[i+j*n]!=expected[j])throw std::runtime_error("Coefficient mismatch");checked++;}
            }
        }
        check(cudaFree(a));check(cudaFree(b));check(cudaFree(out));check(cudaFree(dm));
    }
    std::cout<<"{\"coefficient_checks\":"<<checked<<",\"alias_and_distinct\":true,\"modulus_bits\":[31,50,60]}\n";
}
