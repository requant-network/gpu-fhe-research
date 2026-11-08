# Research program and decisions

A research project by [Requant Network](https://requant.network).

## Completed campaign

Do exact RNS arithmetic improvements survive data movement, and can realistic CKKS workloads and bootstrapping execute on a 16 GB consumer GPU?

The [final report](FINAL_REPORT.md) documents the hypotheses, mathematical contract, two-seed measurements, independent checks, negative outcomes and conclusions. Completion refers to this bounded experimental campaign; it does not mean the field has no open questions.

| Completed experiment | Executable source | Primary evidence |
| --- | --- | --- |
| Large-ring exact RNS/NTT ablations | [large_ntt_study.py](large_ntt_study.py) | [results/large-ntt.json](results/large-ntt.json) |
| Independent Shoup bounds | [validate_shoup.py](validate_shoup.py) | [results/large-ntt.json](results/large-ntt.json) |
| Actual CKKS encrypted square | [native/ckks_study.cpp](native/ckks_study.cpp) | [results/ckks-16384.json](results/ckks-16384.json) |
| Actual unmodified slim bootstrap | [native/bootstrap_study.cpp](native/bootstrap_study.cpp) | [results/bootstrap.json](results/bootstrap.json) |
| Pinned library/build provenance | [collect_heongpu_build.py](collect_heongpu_build.py) | [results/heongpu-build.json](results/heongpu-build.json) |

The matching replication records and complete median/p95 data are indexed in [stage2-summary.csv](results/stage2-summary.csv). [GPU_REPORT.md](GPU_REPORT.md) preserves the preliminary Stage-1 experiments.

## Work beyond this campaign

Arithmetic acceleration is demonstrated; the transfer-inclusive 20% gate is not met. Real CKKS and slim bootstrapping on this consumer GPU are validated as a separate completed feasibility study. The most useful next experiment is to integrate a compatible arithmetic change into a pinned key-switch/rescale/bootstrap path and measure its actual share of application latency. Wider primes, fused basis conversion, key movement, sustained memory pressure and sampled energy remain distinct future studies. The present data do not justify replacing production HEonGPU arithmetic.
