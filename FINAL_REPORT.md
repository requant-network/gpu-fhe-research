# Exact RNS arithmetic and real CKKS workloads: final research report

A research project by [Requant Network](https://requant.network). Campaign completed on 2026-11-09, Asia/Yekaterinburg; raw timestamps use UTC.

## Finding

Exact 31-bit Shoup arithmetic plus tiled NTT scheduling reduces the largest tested resident RNS product latency by about 35.6%. Including PCIe transfers reduces that gain to about 12%, below this project's provisional 20% full-operation target.

The application follow-up executes real public-key CKKS encryption/evaluation/decryption and the unmodified HEonGPU slim bootstrapping preset. Full bootstrapping works on the RTX 5060 Ti **16 GB**: medians are approximately 175–176 ms, and every decoded real slot passes the 0.001 absolute-error gate. The largest observed bootstrap error is about 2.21e-7. Our experimental 31-bit NTT is not integrated into HEonGPU, so these are application feasibility baselines, not an application speedup claim.

## Research questions and decisions

| Question | Evidence | Decision |
| --- | --- | --- |
| Does fixed-twiddle Shoup multiplication outperform runtime modulo at realistic ring sizes? | N = 16,384–65,536, 2/8/16 limbs, full-range residues and exact oracles. | Yes for this implementation and device. |
| Does shared-memory tiling improve the whole polynomial product? | Fair CUDA Graph baseline for all variants; two forward transforms, product, inverse and untwist. | Yes for resident data; transfer-inclusive gain misses the 20% gate. |
| Do arithmetic tests alone establish an encrypted computation result? | Separate real CKKS API harness with all-slot decryption checks. | Real application behavior is now measured separately. |
| Can slim bootstrapping fit and run on 16 GB? | Upstream preset, generated keys, four patterns, two seeds and 280 executions. | Yes for the tested preset and environment. |
| Has our NTT accelerated real CKKS or bootstrapping? | No integration into the upstream 64-bit/RNS/key-switch implementation. | No; retain as a candidate, not a demonstrated application optimization. |

## Exact arithmetic contract

The large transform computes independent negacyclic products modulo each prime p in Z_p[X]/(X^N + 1). Sixteen distinct primes below 2^31 and primitive generators are deterministically constructed. Roots have exact required order. Inputs use the complete residue range, not a small-coefficient shortcut. Limb counts do not constitute a secure ciphertext modulus selection.

For fixed twiddle w, precompute w' = floor(w 2^32 / p). For canonical a, q = high32(a w'), and r = a w - q p satisfies 0 <= r < 2p < 2^32. One conditional subtraction gives the canonical residue. `validate_shoup.py` independently checks 80,576 edge/random products and maximum-ring root orders. The method is established arithmetic; see the [FLINT Shoup algorithm documentation](https://flintlib.org/doc/algorithms/arithmetic/shoup.html).

Three implementations share the ring and output representation: global runtime modulo, global 32-bit Shoup, and tiled Shoup. The tiled path fuses the first ten transform stages inside 1,024-coefficient tiles, pairs the input forward transforms, then performs remaining stages globally; inverse preparation and final untwist are fused where applicable. Every variant uses CUDA Graphs, including the baseline.

All GPU residues match across variants. Arbitrary-precision CPU NTTs independently check channels 0, 1 and the last channel in each case. For four or more channels, zero and maximal residues occupy channels 0 and 1, with a random last channel; two-channel cases retain random inputs in both channels. This explicitly states sampled-channel CPU coverage instead of claiming an independent CPU check of every large tensor element.

## Actual encrypted workloads

The clean [HEonGPU revision](https://github.com/enCRYPTON-labs/HEonGPU/tree/837ffc87aa263bdfebfdfd1d077e5a52c7ae1ed1) is `837ffc87aa263bdfebfdfd1d077e5a52c7ae1ed1` (2.1.1), including its pinned recursive submodules. Original API harnesses are provided in [native/ckks_study.cpp](native/ckks_study.cpp) and [native/bootstrap_study.cpp](native/bootstrap_study.cpp). A CMake hook adds only those executables; upstream library arithmetic remains unchanged. The library declares sec128. This research does not independently audit its security estimates, sparse secret choices or cryptographic implementation.

The square harness uses N=8,192 with scale 2^30/depth 2 and N=16,384 with scale 2^40/depth 3. Actual Q/P prime counts and modulus bit limits are recorded. Every slot is decoded and compared with the squared original value after every warm-up and timed execution, including zero and fixed edge values. Both resident evaluation and encode→encrypt→evaluate→decrypt→decode paths are timed separately.

The slim bootstrap harness uses N=65,536, 32,768 real slots, 48 Galois-key indices, dense key weight 192 and sparse key weight 32. It tests zero, constant 0.2, alternating ±0.2 and seeded uniform inputs in [-0.2,0.2]. A ciphertext copy/reset precedes each measurement; all streams synchronize before/after bootstrapping. Every real slot is decrypted and checked afterwards. Across both seeds, **9,175,040 real-slot comparisons** pass. This is a bootstrap operation benchmark, not a full encrypted application or arbitrary-depth circuit.

## Measured results

All latency cells are **median / nearest-rank p95, milliseconds**.

### Largest exact RNS product: N=65,536, 16 limbs, batch=8

| Seed | Variant | Resident wall | Including transfers |
| --- | --- | --- | --- |
| 20261111 | global_modulo | 8.9330 / 8.9604 | 26.4072 / 26.8435 |
| 20261111 | global_shoup | 8.8110 / 8.8351 | 26.2710 / 26.7056 |
| 20261111 | tiled_shoup | 5.7561 / 5.7827 | 23.2377 / 23.6543 |
| 20261112 | global_modulo | 8.9380 / 8.9610 | 25.3552 / 26.8632 |
| 20261112 | global_shoup | 8.8147 / 8.8405 | 25.2051 / 26.5694 |
| 20261112 | tiled_shoup | 5.7585 / 5.7876 | 22.2977 / 23.7798 |

### Actual CKKS square (all slots checked)

| Seed | N | Q / P primes | Total modulus bits | Square/relin/rescale | Full encrypt/evaluate/decrypt | Max absolute error |
| --- | --- | --- | --- | --- | --- | --- |
| 20261111 | 8192 | 3 / 1 | 181 | 0.0747 / 0.0843 | 0.2231 / 0.2358 | 1.33e-05 |
| 20261112 | 8192 | 3 / 1 | 181 | 0.0752 / 0.0846 | 0.2227 / 0.2283 | 1.22e-05 |
| 20261111 | 16384 | 4 / 4 | 422 | 0.1254 / 0.1321 | 0.3560 / 0.3660 | 2.86e-08 |
| 20261112 | 16384 | 4 / 4 | 422 | 0.1256 / 0.1455 | 0.3559 / 0.3690 | 2.84e-08 |

### Actual slim bootstrap: N=65,536, 32,768 real slots

| Seed | Plaintext pattern | Bootstrap wall | Max absolute error | Output level | Slot comparisons |
| --- | --- | --- | --- | --- | --- |
| 20261111 | zero | 175.3986 / 175.5908 | 1.59e-07 | 12 | 1146880 |
| 20261111 | constant | 175.7035 / 175.9532 | 2.11e-07 | 12 | 1146880 |
| 20261111 | alternating | 175.8058 / 175.9245 | 2.16e-07 | 12 | 1146880 |
| 20261111 | random | 175.9114 / 175.9924 | 2.04e-07 | 12 | 1146880 |
| 20261112 | zero | 175.9508 / 176.0484 | 1.91e-07 | 12 | 1146880 |
| 20261112 | constant | 176.0081 / 176.1211 | 2.2e-07 | 12 | 1146880 |
| 20261112 | alternating | 176.0314 / 176.1607 | 2.12e-07 | 12 | 1146880 |
| 20261112 | random | 176.0584 / 176.2066 | 1.89e-07 | 12 | 1146880 |

Raw records: [large RNS](results/large-ntt.json), [replication](results/large-ntt-replication.json), [CKKS N=8,192](results/ckks-8192.json), [CKKS N=16,384](results/ckks-16384.json), [bootstrap](results/bootstrap.json), [bootstrap replication](results/bootstrap-replication.json). The two CKKS `-replication.json` records retain the second seed.

All cases, both input seeds, median/p95 and timing scopes are retained in [stage2-summary.csv](results/stage2-summary.csv). The first, smaller two-prime NTT/CRT campaign remains in [GPU_REPORT.md](GPU_REPORT.md).

## Timing, memory and limits

Each case uses five warm-ups and thirty measured repetitions. Large-NTT variant order alternates. Each seed is summarized separately; repeated executions reuse case inputs. Twiddle generation, plan/capture construction, compilation and independent oracles are excluded. Resident wall and CUDA event intervals are separate columns. The transfer path adds two full RNS input uploads and one output download, using the measured host-memory/PCIe setup.

The largest arithmetic case reserves 352,322,560 bytes in CuPy's pool; that is not a complete encryption/key memory budget. The bootstrap run records about 10.48 GB active device-pool allocation and a minimum observed free-device reading of about 2.60 GB. These are allocator/synchronization observations, not instrumented instantaneous high-water marks. Successful allocation and completion establish fit for this exact preset; they do not establish fit for all bootstrap parameter sets.

Native CKKS arithmetic excludes ciphertext reset and output decryption; the full path includes encode/encrypt/evaluate/decrypt/decode and synchronization. Bootstrap timing excludes keys/context, ciphertext reset, encryption and decryption. Setup time is retained separately. New seeds change plaintexts; upstream encryption/key generation is not deterministically seeded by our harness. Error checks retain absolute and L2 metrics. No joules, profitability, production security or full-application speedup is inferred.

## Reproduction

The large arithmetic study uses the pinned [CuPy environment](requirements-gpu.txt) and CUDA 12.x headers/runtime. It JIT-compiles its embedded CUDA source. Use Linux and Python 3.12; run without `-O`.

```sh
python validate_shoup.py
export CUDA_PATH=/path/to/cuda-12.8
export PYTHON=/path/to/cupy-venv/bin/python
STUDY=large_ntt_study.py bash run_gpu.sh
STUDY=large_ntt_study.py bash run_gpu.sh --seed 20261112 --output results/large-ntt-replication.json
```

For actual CKKS, install the upstream required development libraries (OpenSSL, GMP, NTL and their dependencies), CMake >=4.0 and a supported host compiler. Our measured build uses CMake 4.1.3, g++ 13.3.0, CUDA 13.3.73, RMM 26.08.00, OpenSSL 3.0.13, GMP 6.3.0, NTL 11.5.1 and GF2X 1.3.0. Exact source, submodule and result bindings are in [heongpu-build.json](results/heongpu-build.json). No private server paths or credentials are required.

```sh
git clone --recursive https://github.com/enCRYPTON-labs/HEonGPU.git upstream-heongpu
git -C upstream-heongpu checkout 837ffc87aa263bdfebfdfd1d077e5a52c7ae1ed1
git -C upstream-heongpu submodule update --init --recursive
cmake -S upstream-heongpu -B build/heongpu -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=120 \
  -DHEONGPU_CUDA_ARCH_FORCE_MANUAL=ON -DHEonGPU_INSTALL_RMM=OFF \
  -DHEonGPU_BUILD_EXAMPLES=OFF -DHEonGPU_BUILD_TESTS=OFF \
  -DHEonGPU_BUILD_BENCHMARKS=OFF \
  -DCMAKE_PROJECT_HEonGPU_INCLUDE="$PWD/native/attach_heongpu.cmake"
cmake --build build/heongpu --target requant_ckks_study requant_bootstrap_study -j 3
CUDA_VISIBLE_DEVICES=0 build/heongpu/requant_ckks_study 8192 20261111 results/ckks-8192.json
CUDA_VISIBLE_DEVICES=0 build/heongpu/requant_ckks_study 16384 20261111 results/ckks-16384.json
CUDA_VISIBLE_DEVICES=0 build/heongpu/requant_bootstrap_study 20261111 results/bootstrap.json
```

Repeat the three executables with seed 20261112 and `-replication.json` output filenames. Use `CMAKE_CUDA_COMPILER` and dependency include/library CMake flags if those installations are not on standard paths. `python collect_heongpu_build.py upstream-heongpu build/heongpu` records your local build after all six native results exist. `python verify_stage2.py` checks source/result provenance and regenerates the CSV on a CPU-only machine; CI reruns CPU/reference and artifact checks, not GPU measurements.

## Conclusion and remaining research

Arithmetic acceleration is demonstrated; the transfer-inclusive 20% gate is not met. Real CKKS and slim bootstrapping on this consumer GPU are validated as a separate completed feasibility study. The most useful next experiment is to integrate a compatible arithmetic change into a pinned key-switch/rescale/bootstrap path and measure its actual share of application latency. Wider primes, fused basis conversion, key movement, sustained memory pressure and sampled energy remain distinct future studies. The present data do not justify replacing production HEonGPU arithmetic.

## Follow-up closure, 12 November 2026

The [follow-up report](FOLLOWUP_REPORT.md) resolves the concrete next steps with new evidence and updated conclusions. Its findings supersede the open-work wording in this historical campaign.
