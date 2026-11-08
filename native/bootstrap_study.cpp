// Requant Network research. Unmodified HEonGPU slim preset, real slot checks.
#include <heongpu/heongpu.hpp>
#include <cuda_runtime.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <random>
#include <stdexcept>
#include <vector>
constexpr auto S=heongpu::Scheme::CKKS;
using Clock=std::chrono::steady_clock;
static void synchronize_device(){auto status=cudaDeviceSynchronize();if(status!=cudaSuccess)throw std::runtime_error(cudaGetErrorString(status));}
static double elapsed(Clock::time_point start){return std::chrono::duration<double,std::milli>(Clock::now()-start).count();}
int main(int argc,char** argv){
    if(argc!=3)return 1;unsigned seed=std::stoul(argv[1]);std::ofstream out(argv[2]);out<<std::setprecision(17);
    try{
        auto setup_start=Clock::now();auto preset=heongpu::CKKSBootstrappingPreset::slim();
        auto context=heongpu::GenHEContext<S>(heongpu::sec_level_type::sec128);preset.apply(context);
        heongpu::MemoryPoolConfig pool;pool.initial_device_bytes=256ULL<<20;pool.max_device_fraction=.95f;
        pool.initial_host_bytes=128ULL<<20;pool.max_host_fraction=.10f;context->generate(pool);
        heongpu::HEKeyGenerator<S> keygen(context);heongpu::Secretkey<S> secret(context,preset.secret_key_hamming_weight);keygen.generate_secret_key(secret);
        heongpu::Publickey<S> public_key(context);keygen.generate_public_key(public_key,secret);
        heongpu::HEEncoder<S> encoder(context);heongpu::HEEncryptor<S> encryptor(context,public_key);
        heongpu::HEDecryptor<S> decryptor(context,secret);heongpu::HEArithmeticOperator<S> operators(context,encoder);
        operators.generate_bootstrapping_params(preset);auto indices=operators.bootstrapping_key_indices();
        auto keys=keygen.bootstrapping_keys(secret,indices,preset.sparse_secret_key_hamming_weight);synchronize_device();double setup_ms=elapsed(setup_start);
        size_t min_free=~size_t(0),total=0;std::mt19937_64 rng(seed);std::uniform_real_distribution<double> draw(-.2,.2);
        out<<"{\"seed\":"<<seed<<",\"preset\":\"slim\",\"n\":"<<preset.poly_modulus_degree<<",\"declared_security_bits\":128,\"galois_keys\":"<<indices.size()
           <<",\"dense_key_weight\":"<<preset.secret_key_hamming_weight<<",\"sparse_key_weight\":"<<preset.sparse_secret_key_hamming_weight
           <<",\"setup_ms\":"<<setup_ms<<",\"warmups\":5,\"samples\":30,\"cases\":[";
        bool first_case=true;
        for(int pattern=0;pattern<4;pattern++){
            std::vector<double> input(preset.poly_modulus_degree/2);
            for(size_t i=0;i<input.size();i++)input[i]=pattern==0?0:pattern==1?.2:pattern==2?(i%2?.2:-.2):draw(rng);
            heongpu::Plaintext<S> plain(context);encoder.encode(plain,input,preset.scale);
            heongpu::Ciphertext<S> original(context);encryptor.encrypt(original,plain);synchronize_device();
            std::vector<double> times;double worst=0,relative=0;size_t slots=0;int output_level=-1;
            for(int iteration=0;iteration<35;iteration++){
                auto active=original;synchronize_device();auto start=Clock::now();auto refreshed=operators.slim_bootstrapping(active,keys);
                synchronize_device();double ms=elapsed(start);output_level=refreshed.level();
                heongpu::Plaintext<S> decoded(context);decryptor.decrypt(decoded,refreshed);std::vector<double> values;encoder.decode(values,decoded);synchronize_device();
                if(values.size()!=input.size())throw std::runtime_error("Bootstrap output shape mismatch");
                double e2=0,s2=0;
                for(size_t i=0;i<input.size();i++){
                    double error=std::abs(values[i]-input[i]);if(!std::isfinite(values[i])||error>.001)throw std::runtime_error("Bootstrap accuracy threshold exceeded");
                    worst=std::max(worst,error);e2+=error*error;s2+=input[i]*input[i];slots++;
                }
                relative=std::max(relative,std::sqrt(s2?e2/s2:e2));size_t free=0;cudaMemGetInfo(&free,&total);min_free=std::min(min_free,free);
                if(iteration>=5)times.push_back(ms);
            }
            if(!first_case)out<<",";first_case=false;
            out<<"{\"pattern\":\""<<(pattern==0?"zero":pattern==1?"constant":pattern==2?"alternating":"random")<<"\",\"output_level\":"<<output_level
               <<",\"slots_checked\":"<<slots<<",\"max_absolute_error\":"<<worst<<",\"error_metric\":\""<<(pattern==0?"absolute_l2":"relative_l2")
               <<"\",\"maximum_l2_error\":"<<relative<<",\"samples_ms\":{\"slim_bootstrap\":[";
            for(size_t i=0;i<times.size();i++){if(i)out<<",";out<<times[i];}out<<"]}}";
            std::cout<<pattern<<" all slots validated; max error "<<worst<<std::endl;
        }
        out<<"],\"observed_total_device_bytes\":"<<total<<",\"minimum_observed_free_device_bytes\":"<<min_free
           <<",\"pool_active_device_bytes\":"<<heongpu::MemoryPool::instance().get_current_device_pool_memory_usage()
           <<",\"scope\":\"Unmodified upstream slim CKKS bootstrap, declared sec128. Every real slot decrypted and checked. Key/context setup, ciphertext reset and decryption excluded from steady-state bootstrap wall time; all streams synchronized. Threshold max absolute error 0.001. No comparison against our 31-bit arithmetic kernels and no independent security audit.\"}\n";
        return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<std::endl;return 2;}
}
