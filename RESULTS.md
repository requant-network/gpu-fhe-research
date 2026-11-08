# Research results

**Completed campaign:** Completed Stage 2: exact large-ring RNS/Shoup/tiled NTT tests, real CKKS encryption/evaluation/decryption, and unmodified slim bootstrapping on RTX 5060 Ti 16 GB. Largest resident arithmetic improves about 35.6%; transfers limit the gain to about 12%. Actual bootstrap takes about 175–176 ms. Our arithmetic kernels are not integrated into the upstream bootstrap.

The [final report](FINAL_REPORT.md) supersedes the preliminary scope and next-step list below. It contains the completed experiments, reproducible commands, negative outcomes and remaining work beyond this campaign. Historical Stage-1 details follow.

Research date: 2026-11-09, Asia/Yekaterinburg. Machine-readable records use UTC.

## CPU correctness

1005 signed centered-CRT/basis-extension cases passed. Fifteen negacyclic products matched independent schoolbook arithmetic, including N=1024. Auxiliary-modulus range and root orders were checked. The small ring modulus is an arithmetic test parameter.

Both Windows/Python 3.12.10 and Linux x86_64/Python 3.12.3 runs passed. Raw records include source hashes and timing scope:

- [Windows baseline](results/cpu-baseline.json)
- [Linux baseline](results/cpu-linux.json)

## GPU campaign

The RTX 5060 Ti campaign has now executed successfully. The initial `cuda/probe.cu` diagnostic passed against its exact CPU fixture. The extended study and independent-seed replication are documented in [GPU_REPORT.md](GPU_REPORT.md), with full source hashes, timings, correctness checks, negative results, and next research decisions.

- [Primary GPU observations](results/gpu-study.json)
- [Independent input-seed replication](results/gpu-replication.json)
- [Environment](results/gpu-environment.json)
- [Reproduction and measurement rules](METHODS.md)

These experiments measure arithmetic and systems behavior. They do not establish full-protocol security, upstream verifier acceptance, or mining revenue.
