# GPU FHE Research

Exact polynomial arithmetic research toward efficient FHE GPU pipelines.

**Stage 0 вЂ” CPU arithmetic baseline and CUDA diagnostic preparation.**

## Research question

Can RNS conversion, polynomial transforms, and key-switch data movement be co-designed to reduce complete bootstrapping cost?

## Current experiment scope

The first experiment computes exact negacyclic products in Z_65537[X]/(X^N+1), using two auxiliary NTT primes and centered CRT reconstruction. It proves the reconstruction range for each tested size and compares with independent quadratic schoolbook multiplication. A third-prime basis-extension check covers signed integers. This is an arithmetic experiment, not an encryption scheme, key-switch implementation, bootstrapping benchmark, or claim of a cryptographic security level.

## Checks

python run.py checks 1005 signed CRT/basis-extension values and 15 polynomial products at N=4,16,64,256,1024. Zero, maximum coefficients, and seeded random values are covered. Primitive-root order is checked for every transform size.

The CUDA diagnostic compares 4096 pointwise modular products against exact Python integers. It does not yet implement the NTT, CRT, or full FHE operations on GPU.

## Reproduce the CPU experiment

Requires Python 3.12 or newer and its standard library. Run without Python's `-O` option, because validation uses assertions.

```sh
python run.py
```

This writes `results/cpu-baseline.json` and regenerates `results/gpu-fixture.bin`. The JSON includes UTC time, environment information, and SHA-256 hashes of the executed experiment sources. The binary fixture is generated locally and excluded from Git.

## Prepare and run the CUDA diagnostic

CUDA 12.8 or newer is required for the Blackwell target used here. Compilation does not execute a GPU workload.

```sh
mkdir -p build
nvcc -std=c++17 -O3 -arch=sm_120 cuda/probe.cu -o build/gpu-check
```

When a GPU is available, regenerate the fixture using `python run.py`, then run:

```sh
CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=0 ./build/gpu-check results/gpu-fixture.bin
```

The diagnostic uploads the fixture, warms up ten launches, times 100 launches using CUDA events, and compares every result with the exact fixture. Its timing covers the diagnostic kernel only. CPU preparation and transfers are outside that timer.

## Research record

- [Research questions and next experiments](RESEARCH.md)
- [Measurement rules](METHODS.md)
- [Observed results and limitations](RESULTS.md)
- [Raw CPU baseline](results/cpu-baseline.json)

## License and contributions

Original experiment code is MIT licensed. References retain their own licenses. Contributions should include a reproducible command, source revision, environment, correctness evidence, and a description of measurement scope. Small negative results are welcome.

## Primary references

- [HEonGPU](https://github.com/enCRYPTON-labs/HEonGPU)
- [WarpDrive](https://zhengfangyu.github.io/assets/papers/HPCA2025.pdf)
- [Chameleon](https://arxiv.org/abs/2410.05934)
- [TIGER](https://arxiv.org/abs/2604.04783)
