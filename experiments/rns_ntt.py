"""Exact negacyclic multiplication and centered CRT. Not an encryption scheme."""
import random
import time

PRIMES = ((2013265921, 31), (1811939329, 13))
Q = 65537


def ntt(values, prime, root, inverse=False):
    result = values[:]
    n = len(values)
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            result[i], result[j] = result[j], result[i]
    width = 2
    while width <= n:
        step = pow(root, n // width, prime)
        if inverse:
            step = pow(step, -1, prime)
        for start in range(0, n, width):
            weight = 1
            for offset in range(width // 2):
                left = start + offset
                a, b = result[left], result[left + width // 2] * weight % prime
                result[left] = (a + b) % prime
                result[left + width // 2] = (a - b) % prime
                weight = weight * step % prime
        width *= 2
    if inverse:
        inverse_n = pow(n, -1, prime)
        result = [x * inverse_n % prime for x in result]
    return result


def multiply_mod(a, b, prime, generator):
    n = len(a)
    psi = pow(generator, (prime - 1) // (2 * n), prime)
    assert pow(psi, n, prime) == prime - 1
    weights = [pow(psi, i, prime) for i in range(n)]
    root = psi * psi % prime
    fa = ntt([x * w % prime for x, w in zip(a, weights)], prime, root)
    fb = ntt([x * w % prime for x, w in zip(b, weights)], prime, root)
    product = ntt([x * y % prime for x, y in zip(fa, fb)], prime, root, True)
    return [x * pow(w, -1, prime) % prime for x, w in zip(product, weights)]


def centered_crt(a, b):
    p0, p1 = PRIMES[0][0], PRIMES[1][0]
    value = a + p0 * ((b - a) * pow(p0, -1, p1) % p1)
    modulus = p0 * p1
    return value - modulus if value > modulus // 2 else value


def schoolbook(a, b):
    result = [0] * len(a)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            index = i + j
            result[index % len(a)] += x * y if index < len(a) else -x * y
    return [x % Q for x in result]


def experiment():
    rng = random.Random(20261109)
    extension_prime = 469762049
    modulus = PRIMES[0][0] * PRIMES[1][0]
    extension_checks = 0
    for value in [0, 1, -1, modulus // 2, -(modulus // 2)] + [rng.randrange(-(modulus // 2), modulus // 2) for _ in range(1000)]:
        recovered = centered_crt(value % PRIMES[0][0], value % PRIMES[1][0])
        assert recovered == value
        assert recovered % extension_prime == value % extension_prime
        extension_checks += 1
    cases = []
    for n in (4, 16, 64, 256, 1024):
        assert 2 * n * (Q - 1) ** 2 < modulus
        for pattern in ('zero', 'max', 'random'):
            a = [0 if pattern == 'zero' else Q - 1 if pattern == 'max'
                 else rng.randrange(Q) for _ in range(n)]
            b = [rng.randrange(Q) for _ in range(n)]
            start = time.perf_counter()
            residues = [multiply_mod(a, b, p, g) for p, g in PRIMES]
            result = [centered_crt(x, y) % Q for x, y in zip(*residues)]
            elapsed = time.perf_counter() - start
            assert result == schoolbook(a, b)
            cases.append({'n': n, 'pattern': pattern, 'rns_ntt_seconds': elapsed, 'verified': True})
    return {'basis_extension_checks': extension_checks, 'polynomial_cases': cases,
            'scope': 'Small exact arithmetic baseline. No ciphertexts, key switching, bootstrapping, or security estimate.'}


def fixture():
    rng = random.Random(7)
    prime = PRIMES[0][0]
    a = [rng.randrange(prime) for _ in range(4096)]
    b = [rng.randrange(prime) for _ in range(4096)]
    return 0, prime, a, b, [x * y % prime for x, y in zip(a, b)]
