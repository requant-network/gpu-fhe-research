"""Independent integer checks for the 32-bit Shoup contract used by GPU NTTs."""
import json
import pathlib
import random

assert __debug__
rng=random.Random(24681357)
basis=json.loads(pathlib.Path('results/large-ntt.json').read_text())['basis']
checked=0
for p,g in basis:
    assert 0<p<1<<31 and (p-1)%(2*65536)==0
    root=pow(g,(p-1)//(2*65536),p)
    assert pow(root,65536,p)==p-1
    edges=(0,1,p//2,p//2+1,p-2,p-1)
    pairs=[(a,w) for a in edges for w in edges]
    pairs.extend((rng.randrange(p),rng.randrange(p)) for _ in range(5000))
    for a,w in pairs:
        quotient=(w<<32)//p
        q=(a*quotient)>>32
        residual=(a*w-q*p)&0xffffffff
        assert q<=a*w//p and residual<2*p
        actual=residual-p if residual>=p else residual
        assert actual==a*w%p
        checked+=1
print(checked,'Shoup edge/random products and all large-ring root orders passed')
