// Requant Network research. Uses the unmodified HEonGPU public CKKS API.
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
#include <string>
#include <vector>

constexpr auto Scheme=heongpu::Scheme::CKKS;
using Clock=std::chrono::steady_clock;
static void synchronize_device(){auto s=cudaDeviceSynchronize();if(s!=cudaSuccess)throw std::runtime_error(cudaGetErrorString(s));}
static double milliseconds(Clock::time_point start){return std::chrono::duration<double,std::milli>(Clock::now()-start).count();}
static void array(std::ostream& out,const std::vector<double>& values){out<<"[";for(size_t i=0;i<values.size();i++){if(i)out<<",";out<<values[i];}out<<"]";}
int main(int argc,char** argv){
    if(argc!=4){std::cerr<<"Usage: ckks_study N seed result.json\n";return 1;}
    int n=std::stoi(argv[1]);unsigned seed=std::stoul(argv[2]);std::ofstream result(argv[3]);result<<std::setprecision(17);
    if(!result|| (n!=8192&&n!=16384))return 1;
    try{
        auto setup_start=Clock::now();
        heongpu::HEParams<Scheme> specification;specification.poly_modulus_degree=n;
        specification.security_level=heongpu::sec_level_type::sec128;
        specification.scale_bit_size=n==8192?30:40;specification.multiplicative_depth=n==8192?2:3;
        auto parameters=specification.generate();auto context=parameters.make_context();
        heongpu::MemoryPoolConfig pool;pool.initial_device_bytes=64ULL<<20;pool.max_device_fraction=.90f;
        pool.initial_host_bytes=64ULL<<20;pool.max_host_fraction=.10f;context->generate(pool);
        heongpu::HEKeyGenerator<Scheme> keygen(context);heongpu::Secretkey<Scheme> secret(context);keygen.generate_secret_key(secret);
        heongpu::Publickey<Scheme> public_key(context);keygen.generate_public_key(public_key,secret);
        heongpu::Relinkey<Scheme> relin(context);keygen.generate_relin_key(relin,secret);
        heongpu::HEEncoder<Scheme> encoder(context);heongpu::HEEncryptor<Scheme> encryptor(context,public_key);
        heongpu::HEDecryptor<Scheme> decryptor(context,secret);heongpu::HEArithmeticOperator<Scheme> evaluator(context,encoder);
        std::mt19937_64 rng(seed);std::uniform_real_distribution<double> draw(-.75,.75);
        std::vector<double> input(n/2);for(auto& x:input)x=draw(rng);input[0]=0;input[1]=.5;input[2]=-.5;input[3]=.75;
        heongpu::Plaintext<Scheme> plain(context);encoder.encode(plain,input,specification.scale());
        heongpu::Ciphertext<Scheme> encrypted(context);encryptor.encrypt(encrypted,plain);synchronize_device();double setup_ms=milliseconds(setup_start);
        auto evaluate=[&](auto& active){evaluator.multiply_inplace(active,active);evaluator.relinearize_inplace(active,relin);evaluator.rescale_inplace(active);};
        double max_error=0,max_relative_l2=0;size_t slots_checked=0,min_free=~size_t(0),total=0;
        auto validate=[&](auto& active){
            heongpu::Plaintext<Scheme> decoded(context);decryptor.decrypt(decoded,active);std::vector<double> values;encoder.decode(values,decoded);synchronize_device();
            if(values.size()!=input.size())throw std::runtime_error("Wrong decoded vector size");
            double error2=0,scale2=0;
            for(size_t i=0;i<input.size();i++){double expected=input[i]*input[i],e=std::abs(values[i]-expected);
                if(!std::isfinite(values[i])||e>.001)throw std::runtime_error("CKKS square accuracy failed");
                max_error=std::max(max_error,e);error2+=e*e;scale2+=expected*expected;slots_checked++;}
            max_relative_l2=std::max(max_relative_l2,std::sqrt(error2/scale2));
            size_t free=0;cudaMemGetInfo(&free,&total);min_free=std::min(min_free,free);
        };
        std::vector<double> arithmetic,full;
        for(int iteration=0;iteration<35;iteration++)for(int j=0;j<2;j++){
            int mode=iteration%2?1-j:j;
            heongpu::Ciphertext<Scheme> active(context);heongpu::Plaintext<Scheme> encoded(context),decoded(context);
            std::vector<double> values;
            if(!mode)active=encrypted;synchronize_device();auto start=Clock::now();
            if(mode){encoder.encode(encoded,input,specification.scale());encryptor.encrypt(active,encoded);}
            evaluate(active);
            if(mode){decryptor.decrypt(decoded,active);encoder.decode(values,decoded);}
            synchronize_device();double elapsed=milliseconds(start);validate(active);
            if(iteration>=5)(mode?full:arithmetic).push_back(elapsed);
        }
        result<<"{\"n\":"<<n<<",\"seed\":"<<seed<<",\"slots\":"<<n/2<<",\"warmups\":5,\"samples\":30,\"setup_ms\":"<<setup_ms
              <<",\"declared_security_bits\":128,\"q_prime_count\":"<<parameters.coeff_modulus.size()<<",\"p_prime_count\":"<<parameters.special_modulus.size()
              <<",\"total_modulus_bits\":"<<parameters.total_bit_count()<<",\"security_bit_limit\":"<<parameters.max_bit_count()
              <<",\"key_switch_digits\":"<<parameters.digit_count()<<",\"scale_bits\":"<<specification.scale_bit_size
              <<",\"max_absolute_error\":"<<max_error<<",\"max_relative_l2_error\":"<<max_relative_l2<<",\"slots_checked\":"<<slots_checked
              <<",\"observed_total_device_bytes\":"<<total<<",\"minimum_observed_free_device_bytes\":"<<min_free
              <<",\"pool_active_device_bytes\":"<<heongpu::MemoryPool::instance().get_current_device_pool_memory_usage()
              <<",\"samples_ms\":{\"multiply_relinearize_rescale\":";array(result,arithmetic);result<<",\"encode_encrypt_evaluate_decrypt_decode\":";array(result,full);
        result<<"},\"scope\":\"Actual upstream CKKS public-key encryption and homomorphic square. Arithmetic timer excludes input ciphertext reset and output decryption. Full timer includes encode, encrypt, evaluate, decrypt, decode and synchronization. Setup/keys excluded from steady-state timings. Library sec128 declaration is not an independent security audit.\"}\n";
        std::cout<<n<<" all slots verified; max error "<<max_error<<"\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 2;}
}
