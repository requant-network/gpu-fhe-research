# Research plan

## Question

Can RNS conversion, polynomial transforms, and key-switch data movement be co-designed to reduce complete bootstrapping cost?

## Hypothesis and boundaries

The first experiment computes exact negacyclic products in Z_65537[X]/(X^N+1), using two auxiliary NTT primes and centered CRT reconstruction. It proves the reconstruction range for each tested size and compares with independent quadratic schoolbook multiplication. A third-prime basis-extension check covers signed integers. This is an arithmetic experiment, not an encryption scheme, key-switch implementation, bootstrapping benchmark, or claim of a cryptographic security level.

## Completed first experiment

python run.py checks 1005 signed CRT/basis-extension values and 15 polynomial products at N=4,16,64,256,1024. Zero, maximum coefficients, and seeded random values are covered. Primitive-root order is checked for every transform size.

## Completed GPU campaign

[GPU_REPORT.md](GPU_REPORT.md) records the executed two-seed campaign, mathematical contract, independent checks, raw timings, ablations, negative findings and next decisions. All study sources and records are public. This extends the CPU baseline without claiming a complete cryptographic protocol.

## Next experiments

1. Scale the tested GPU NTT/CRT pipeline to multi-block transforms and realistic RNS chains; compare with a pinned optimized library.
2. Profile key switching and bootstrapping in a pinned public library at its documented security parameters.
3. Investigate CKKS/TFHE switching only with matched precision, security parameters, and conversion cost.

## Evidence required

Report a full-operation comparison against a pinned baseline, independent correctness checks, memory requirements, and energy observations. Distinguish algorithmic improvement from changed workloads or weaker validation. An upstream verifier must accept any claimed protocol improvement.

## Sources

- [HEonGPU](https://github.com/enCRYPTON-labs/HEonGPU)
- [WarpDrive](https://zhengfangyu.github.io/assets/papers/HPCA2025.pdf)
- [Chameleon](https://arxiv.org/abs/2410.05934)
- [TIGER](https://arxiv.org/abs/2604.04783)
