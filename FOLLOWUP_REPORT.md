# Compatible 64-bit integration and application decision

Requant Network, 12 November 2026. This supplement resolves the compatible native-arithmetic integration question from the [historical report](FINAL_REPORT.md). It does not replace CKKS primes with the earlier 31-bit experimental NTT primes.

## Actual library change and exact checks

The isolated [attributed patch](patches/square-alias.patch) targets HEonGPU commit `837ffc87aa263bdfebfdfd1d077e5a52c7ae1ed1`. In the actual 64-bit ciphertext cross-product kernel, equal input addresses imply equal cross terms. The candidate reuses one modular product for a square instead of computing it twice. General two-operand multiplication retains its original path, and the modulus representation, security parameters, key switching and rescaling rules are unchanged. The original upstream checkout and library/binaries remain untouched.

[The independent coefficient program](native/square_check.cu) checks 147,456 output coefficients against CPU unsigned-128-bit modular arithmetic, including zero/p-1 boundaries, random inputs, aliased and distinct operands, and 31/50/60-bit moduli. Every coefficient matches. This checks the modified machine arithmetic directly, in addition to later approximate plaintext checks.

The build script reconstructs the original compiler/link commands, replaces one kernel object in a **copy** of the native static library, and rebuilds device/host links. It uses no duplicate-symbol override or suppressed validation. The paired baseline links the unmodified archive; both variants use identical generated application harnesses and the same explicit host-pool maximum.

## Resource setup preserved

The [preflight record](results/integration-preflight.json) retains the observed setup failures. Installed GMP/NTL include and runtime-library paths must be provided in this non-system dependency installation. The original fractional host-pool maximum also rejected setup because the library used immediately free RAM: roughly 493 MiB was free while about 54.6 GiB was reclaimably available. Ten percent of the former was below the original 64/128 MiB initial pool sizes.

The new paired harnesses change only that maximum assignment to an explicit **256 MiB** via the supported API, retaining the original 64/128 MiB initial sizes. This budget fits the observed free RAM, and every native pool-size/availability check remains enabled. Security/accuracy parameters and the old executed harness sources are preserved. Comparing these new variants is valid; their setup policy is not silently equated to the older campaign's fractional host-pool policy.

## Complete CKKS and bootstrap results

The actual CKKS application performs public-key encryption and a homomorphic square followed by relinearization/rescale. Arithmetic timing excludes input ciphertext reset and decryption. The separate full boundary includes encode, encrypt, evaluate, decrypt, decode and synchronization. Setup/keys are retained separately. Every timed result is decrypted and all slots must satisfy the original 0.001 error gate. Library sec128 declarations are retained, not reinterpreted as an independent security audit.

Each native harness uses five warm-ups and thirty measured samples. Whole-harness variant order reverses across the two input seeds; it is not an interleaved within-iteration paired test. Medians, milliseconds:

| Seed | N | Variant | Square/relinearize/rescale | Encode through decode |
| --- | ---: | --- | ---: | ---: |
| 20261112 | 8192 | baseline | 0.075779 | 0.226675 |
| 20261112 | 8192 | square_alias | 0.076199 | 0.225209 |
| 20261112 | 16384 | baseline | 0.127848 | 0.357910 |
| 20261112 | 16384 | square_alias | 0.127812 | 0.356268 |
| 20261212 | 8192 | square_alias | 0.076688 | 0.222904 |
| 20261212 | 8192 | baseline | 0.076269 | 0.225941 |
| 20261212 | 16384 | square_alias | 0.128511 | 0.358713 |
| 20261212 | 16384 | baseline | 0.128302 | 0.358712 |

The unchanged slim bootstrap preset at N=65536 checks every slot for zero, constant, alternating and random inputs. The same five/thirty design measures the complete native bootstrap (setup/key generation excluded):

| Seed | Variant | Zero, ms | Constant, ms | Alternating, ms | Random, ms |
| --- | --- | ---: | ---: | ---: | ---: |
| 20261112 | baseline | 175.7272 | 175.8906 | 176.0574 | 176.1107 |
| 20261112 | square_alias | 176.1536 | 176.2731 | 176.3699 | 176.4319 |
| 20261212 | square_alias | 176.3639 | 176.4783 | 176.5206 | 176.5539 |
| 20261212 | baseline | 176.6059 | 176.6613 | 176.7016 | 176.7417 |

There is **no material replicated application gain**. CKKS arithmetic differences are below one percent and change interpretation with size; bootstrap changes by roughly two tenths of a percent and reverses sign with cohort/order. Do not describe those differences as an established speedup. All tested outputs remain accurate, but removing one modular product from one kernel does not establish useful acceleration of the complete application. The data do not measure the exact fraction of bootstrap time spent in that kernel, so no unmeasured phase-share or Amdahl claim is made.

## GPU-reported energy, measured separately

[energy_study.py](energy_study.py) samples read-only NVML power and cumulative GPU energy while each complete paired bootstrap process executes, including setup, all five warm-ups and thirty samples for each of four input patterns. The official native API reports cumulative energy in millijoules since driver reload; its start/end difference is the primary GPU-reported quantity. The trapezoidal integral of the sampled power is retained independently. This is not CPU or whole-system energy and is not the energy of only one steady-state bootstrap.

| Seed | Variant | Observed process envelope, s | GPU-reported counter, J | Sampled power integral, J | Samples |
| --- | --- | ---: | ---: | ---: | ---: |
| 20261112 | baseline | 25.702 | 3605.915 | 3828.820 | 243 |
| 20261112 | square_alias | 25.621 | 3678.671 | 4011.960 | 243 |
| 20261212 | square_alias | 25.679 | 3714.536 | 4038.816 | 243 |
| 20261212 | baseline | 25.675 | 3732.133 | 4053.240 | 243 |

There are only two whole-process energy observations per variant. The candidate consumes more reported GPU energy in the first pair and slightly less in the reversed-order pair; a repeatable energy reduction is not established. Power integration and the cumulative counter differ by about 6–9% under load. The ten-second idle probe also disagrees (counter 126.24 J versus sampled integral 89.83 J), so neither is presented as a calibrated wall meter or silently substituted for the other. The idle probe is not subtracted from the gross process totals. Raw timestamps, sensor values and actual maximum sampling gaps are retained in [energy-study.json](results/energy-study.json); [energy-summary.csv](results/energy-summary.csv) is independently regenerated by CPU CI.

No readable CPU package energy counter was exposed through the searched powercap/hwmon interfaces for this account. Accordingly these data do not establish CPU-versus-GPU energy efficiency or total application electricity cost. The second card was occupied during these energy observations; after the user's later authorization its services were temporarily stopped for the separate two-GPU erasure campaign. These are different experimental conditions, not one pooled benchmark.

## Decision and reproduction

Retain the unmodified native arithmetic for this workload: the candidate is mathematically compatible and experimentally correct but fails the useful application-performance gate. The earlier 31-bit Shoup microbenchmarks remain a distinct arithmetic result; they do not justify replacing the actual wider-prime CKKS pipeline.

[ integration_study.py](integration_study.py) recreates the isolated patch, paired executables, exact coefficient qualification and two-seed application campaign from the documented existing native build. Provide the installed dependency include paths through `CPATH` and library paths through `LD_LIBRARY_PATH`; invoke `python integration_study.py UPSTREAM BUILD --ninja NINJA`. [The evidence](results/integration-study.json) retains generated harness hashes, source/archive/binary hashes, parameters, all timing samples, all-slot errors, memory counters and scope. `python verify_followups.py` checks these bindings and derives the full [median/p95 table](results/followup-summary.csv). CI preserves all original exact RNS/NTT and application-evidence checks; it does not rerun GPU timing.

GPU campaigns run serially on the same RTX 5060 Ti. Clocks, power limits and unrelated services are unchanged. Production security, whole-system energy efficiency and heterogeneous multi-GPU FHE scaling are not inferred.
