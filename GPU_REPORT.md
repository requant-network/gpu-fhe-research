# GPU negacyclic arithmetic research

Research by [Requant Network](https://requant.network). Campaign date: 9 November 2026, Asia/Yekaterinburg; raw records use UTC.

This is an executed, reproducible research campaign on a GeForce RTX 5060 Ti 16 GB (36 SMs), paired with an AMD Ryzen 5 5500. The host exposes PCIe Gen 3, with an observed x8 link in the environment snapshot. Do not extrapolate transfer timings to a Gen 5 workstation or a datacenter GPU. The software record reports Python 3.12.3, NumPy 2.2.6, CuPy 13.6.0, NVRTC 12.8, runtime API 12090 and driver 610.43.03. CUDA compilation uses 12.8.61 unless explicitly stated otherwise.

Each variant has five warm-ups and thirty measured repetitions per case. A second campaign changes the input seed from 20261109 to 20261110. Tables show milliseconds. p95 uses the nearest-rank definition. Repetitions reuse each case's inputs; they do not establish population confidence intervals. Default dynamic clocks were retained. The experiments ran sequentially on the released GPU.

[Primary raw results](results/gpu-study.json), [independent-seed replication](results/gpu-replication.json), [complete median/p95 table](results/gpu-summary.csv), [environment](results/gpu-environment.json), [methods](METHODS.md), and [executable study](gpu_study.py) are part of this record. `python summarize_results.py` verifies source hashes and regenerates the CSV. Correctness checks run outside the measured intervals.

## Question and mathematical contract

Can stage fusion, device CRT, constant-prime specialization and CUDA Graphs improve a complete polynomial multiplication path, rather than a pointwise product alone?

The operation is a*b in Z_65537[X]/(X^N+1), for N = 256, 1024 and 2048. Coefficients are canonical integers in [0,65536]. Two NTT-friendly primes are 2013265921 and 1811939329, with primitive generators 31 and 13. A 2N-th root twists each negacyclic transform into an ordinary cyclic NTT. Forward transforms, pointwise multiplication, inverse transforms, untwisting, centered CRT and reduction modulo 65537 complete the operation.

For every size the code checks 2*N*(65536)^2 < p0*p1. Thus the true signed integer convolution coefficient lies strictly inside the centered reconstruction range. This range check is essential: a product modulo unrelated auxiliary primes cannot generally be reduced modulo the target modulus without it. These small parameters are arithmetic test parameters, not a secure BFV/CKKS parameter set.

## Variants and independent checks

- **Global:** one global-memory kernel per radix-2 stage; CPU centered CRT.
- **Shared:** one block per polynomial and prime; forward transforms, pointwise multiplication and inverse transform share a kernel; CPU CRT.
- **Shared + GPU CRT:** the same fused transforms and reconstruction on device.
- **Specialized + GPU CRT:** the same operations with a separately JIT-compiled constant prime for each modulus, allowing compiler strength reduction instead of runtime integer division.
- **Global graph + GPU CRT:** captured global-stage kernels, removing most Python dispatch gaps.
- **Specialized graph + GPU CRT:** captured fused, constant-prime transforms and device CRT.

Batches are 1, 16 and 128. Larger batches include zero and maximum-coefficient products in addition to random inputs. All transformed residue arrays match across the global, shared and specialized implementations. CPU arbitrary-precision NTTs independently check selected zero, maximum and random rows: 42 row-pairs across both seeds, each in both primes. At N=256, 14 row-products also match independent quadratic schoolbook multiplication. Every graph output and every timed full-path result matches the reference reconstruction. The Stage-0 suite separately checks signed CRT boundaries and schoolbook products through N=1024.

The shared kernel requires 12*N bytes of dynamic shared memory, at most 24 KiB here. Twiddle tables and plans are precomputed. These experiments fit on the available 16 GB card; a peak-VRAM profile was not collected.

## Transfer-inclusive results

These wall timings include copies into preallocated GPU input buffers, GPU polynomial multiplication, output transfer and reconstruction. CPU-CRT variants transfer two residue arrays and reconstruct on CPU; GPU-CRT variants transfer the final coefficients only. They exclude twiddle/plan construction, input generation and CPU oracle work. Graph capture is also excluded. This is a full polynomial-arithmetic path, not a full FHE application.

| N | Batch | Global + CPU CRT | Shared + CPU CRT | Shared + GPU CRT | Global graph + GPU CRT | Specialized graph + GPU CRT | Best graph p95 | Replication best graph |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 256 | 1 | 0.5096 | 0.1133 | 0.0678 | 0.0935 | 0.0425 | 0.0446 | 0.0438 |
| 256 | 16 | 0.5563 | 0.1531 | 0.0721 | 0.1039 | 0.0471 | 0.0540 | 0.0476 |
| 256 | 128 | 0.9002 | 0.5391 | 0.1448 | 0.1848 | 0.1222 | 0.1282 | 0.1217 |
| 1024 | 1 | 0.6138 | 0.1686 | 0.1188 | 0.1132 | 0.0597 | 0.0620 | 0.0599 |
| 1024 | 16 | 0.7850 | 0.3439 | 0.1398 | 0.1514 | 0.0903 | 0.0992 | 0.0906 |
| 1024 | 128 | 2.1415 | 1.8774 | 0.4609 | 0.5201 | 0.3844 | 0.3962 | 0.3895 |
| 2048 | 1 | 0.6785 | 0.2585 | 0.2019 | 0.1227 | 0.0866 | 0.0879 | 0.0868 |
| 2048 | 16 | 1.0262 | 0.6375 | 0.2645 | 0.2100 | 0.1548 | 0.1596 | 0.1546 |
| 2048 | 128 | 4.1354 | 3.9718 | 0.9473 | 0.9661 | 0.7470 | 0.7642 | 0.7453 |

The dramatic ratio against the simple global/CPU-CRT baseline combines several effects. The graph-to-graph comparison is the more useful guard against claiming that Python launch overhead is a new arithmetic breakthrough. It retains the same GPU reconstruction and output size on both sides.

## Findings and negative evidence

1. **Fusion alone is insufficient.** Most of the shared-memory transform gain disappears at the largest batch when two residue arrays still return for CPU reconstruction. The final raw records retain this small full-path benefit, alongside the much faster resident path.
2. **Device CRT has a substantial systems effect.** It removes host integer-array operations and halves residue-output traffic. This is particularly valuable for the larger batches on this PCIe Gen 3 host.
3. **Constant-prime specialization is worth retaining.** It preserves exact residues while reducing repeated runtime-modulus costs. This is a compiler/representation choice, not a new number-theoretic algorithm.
4. **CUDA Graphs are a necessary baseline.** They eliminate much of the apparent global-stage launch penalty. The optimized fused path still wins in the graph-to-graph comparison, but by a smaller ratio than against the original host-dispatched baseline.
5. **The shared-memory design has a hard scaling boundary.** N=2048 is a small ring. A one-block design cannot be extrapolated directly to larger cryptographic rings, longer RNS bases, key switching, or bootstrapping.

The full CSV also provides resident wall and CUDA-event stream elapsed times. Event measurements of uncaptured global kernels contain host enqueue gaps; they are not an instruction-throughput measurement. CPU allocation, OS activity and pageable transfers make the largest host-CRT measurements variable, so both seeds and p95 remain visible.

## Related work and research decision

[Shivdikar et al., 2022](https://arxiv.org/abs/2209.01290) already studied GPU modular reduction, shared-memory NTTs and fusion with pointwise products. Our result is a reproducible implementation/ablation on this specific Blackwell consumer GPU; it does not claim these techniques are new or outperform that work. [HEonGPU](https://github.com/enCRYPTON-labs/HEonGPU) is a relevant full-system comparison target, not a baseline measured in this campaign.

**Continue this direction, with a parameter-scale gate.** The next necessary experiment is a multi-block/tiled NTT for N=16384 and above, a realistic RNS chain, and a pinned library comparison using identical arithmetic. Then measure ciphertext multiplication plus relinearization/rescaling and key-memory traffic. Keep device reconstruction and a graph baseline in every comparison. Adopt the optimization for an actual FHE system only if its complete operation still improves by the project's 20% gate with unchanged security parameters.

This campaign contains no encryption, keys, security estimate, key switching, bootstrapping, encrypted service or network acceptance test. It establishes exact polynomial-arithmetic behavior and a systems optimization path. Energy and revenue remain unmeasured.
