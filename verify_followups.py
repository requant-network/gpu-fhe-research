"""CPU replay of follow-up evidence, provenance and derived timing summaries."""
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import median
assert __debug__
PATTERNS = ('integration-study.json','integration-preflight.json','energy-study.json')
paths=sorted(set(p for pattern in PATTERNS for p in Path('results').glob(pattern)))
assert len(paths)==3,(len(paths),[p.name for p in paths])
records={p.name:json.loads(p.read_text()) for p in paths}
def binding(name,expected,result=False):
 p=(Path('results')/name) if result else Path(name)
 assert not Path(name).is_absolute() and ':' not in name and '..' not in Path(name).parts
 assert hashlib.sha256(p.read_bytes()).hexdigest()==expected,(p,expected)
def provenance(r):
 if isinstance(r,dict):
  for key,v in r.items():
   if key in ('source_sha256','artifacts_sha256','public_artifacts_sha256','result_sha256'):
    for name,expected in v.items():binding(name,expected,key=='result_sha256')
   elif isinstance(v,(dict,list)):provenance(v)
 elif isinstance(r,list):
  for v in r:provenance(v)
for r in records.values():provenance(r)
assert len(records['integration-preflight.json']['failures'])==3
r=records['integration-study.json'];assert r['coefficient_qualification']['coefficient_checks']==147456
assert r['coefficient_qualification']['alias_and_distinct'] and len(r['cases'])==12
assert r['archive_sha256']['baseline']!=r['archive_sha256']['square_alias']
for name in ('ckks','bootstrap'):
 text=Path(f'native/{name}_study.cpp').read_text()
 assert text.count('pool.max_host_fraction=.10f;')==1
 generated=text.replace('pool.max_host_fraction=.10f;','pool.max_host_bytes=256ULL<<20;')
 assert hashlib.sha256(generated.encode()).hexdigest()==r['harnesses'][name]['generated_source_sha256']
 assert r['harnesses'][name]['max_host_pool_bytes']==256<<20
for c in r['cases']:
 v=c['result'];assert v['seed']==c['seed'] and v['samples']==30 and v['warmups']==5
 assert v['declared_security_bits']==128
 if c['application']=='ckks':
  assert v['max_absolute_error']<=.001 and v['total_modulus_bits']<=v['security_bit_limit']
 else:assert len(v['cases'])==4 and all(x['max_absolute_error']<=.001 for x in v['cases'])

energy=records['energy-study.json'];assert len(energy['cases'])==4
energy_rows=[]
for c in energy['cases']:
 assert c['exit_code']==0 and len(c['samples'])>=20 and c['observed_seconds']>1
 assert c['binary_sha256']==r['binary_sha256']['bootstrap'][c['variant']]
 native=c['native_result'];assert len(native['cases'])==4 and native['seed']==c['seed']
 assert all(x['max_absolute_error']<=.001 for x in native['cases'])
 samples=c['samples'];assert all(a['t_seconds']<=b['t_seconds'] for a,b in zip(samples,samples[1:]))
 assert all(math.isfinite(x['power_mw']) and x['power_mw']>=0 for x in samples)
 integral=sum((b['t_seconds']-a['t_seconds'])*(a['power_mw']+b['power_mw'])/2000 for a,b in zip(samples,samples[1:]))
 assert math.isclose(integral,c['power_integral_joules'],rel_tol=1e-12)
 if c['gpu_counter_joules'] is not None:
  assert c['gpu_counter_joules']==(samples[-1]['energy_mj']-samples[0]['energy_mj'])/1000
 energy_rows.append(dict(seed=c['seed'],variant=c['variant'],process_observed_seconds=c['observed_seconds'],
                         gpu_reported_counter_joules=c['gpu_counter_joules'],sampled_power_integral_joules=integral,
                         samples=len(samples),maximum_sample_gap_seconds=c['maximum_sample_gap_seconds']))
with Path('results/energy-summary.csv').open('w',newline='') as out:
 writer=csv.DictWriter(out,fieldnames=list(energy_rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(energy_rows)

rows=[]
def timings(value,labels,route=''):
 if isinstance(value,list):
  assert len(value)==30 and all(isinstance(v,(int,float)) and math.isfinite(v) and v>=0 for v in value),(labels,route)
  rows.append(dict(**labels,variant_scope=route,median_ms=median(value),p95_ms=sorted(value)[28],repetitions=len(value)))
 elif isinstance(value,dict):
  for key,v in value.items():timings(v,labels,(route+'/' if route else '')+key)
for name,r in records.items():
 if name=='energy-study.json':continue
 for index,c in enumerate(r.get('cases',[])):
  labels=dict(file=name,case=index,seed=c.get('seed',r.get('seed','')),**{key:c.get(key,'') for key in ('application','n','m','k','p','columns','steps','payload_bytes','batch','variant','pattern')})
  v=c.get('result',c)
  for nested in v.get('cases',[]):
   timings(nested['samples_ms'],dict(labels,pattern=nested['pattern']),'samples_ms')
  for key in ('samples','samples_ms','resident_graph_device_ms'):
   if isinstance(v.get(key),(dict,list)):timings(v[key],labels,key)
if rows:
 with Path('results/followup-summary.csv').open('w',newline='') as out:
  writer=csv.DictWriter(out,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
print(len(records),'follow-up records validated;',len(rows),'median/p95 timing rows')
