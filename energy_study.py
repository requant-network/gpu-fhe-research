"""GPU-reported energy of complete, independently checked bootstrap processes."""
import ctypes as ct
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time


def main():
    assert __debug__
    lib=ct.CDLL('libnvidia-ml.so.1')
    lib.nvmlDeviceGetHandleByIndex_v2.argtypes=[ct.c_uint,ct.POINTER(ct.c_void_p)]
    lib.nvmlDeviceGetPowerUsage.argtypes=[ct.c_void_p,ct.POINTER(ct.c_uint)]
    lib.nvmlDeviceGetTotalEnergyConsumption.argtypes=[ct.c_void_p,ct.POINTER(ct.c_ulonglong)]
    lib.nvmlDeviceGetName.argtypes=[ct.c_void_p,ct.c_void_p,ct.c_uint]
    assert lib.nvmlInit_v2()==0
    device=ct.c_void_p();assert lib.nvmlDeviceGetHandleByIndex_v2(0,ct.byref(device))==0
    name=ct.create_string_buffer(96);assert lib.nvmlDeviceGetName(device,name,96)==0
    assert '5060 Ti' in name.value.decode()
    build=Path('build/square-integration');integration=Path('results/integration-study.json')
    reference=json.loads(integration.read_text());cases=[]
    def sample(start):
        power=ct.c_uint();energy=ct.c_ulonglong();begin=time.monotonic()
        assert lib.nvmlDeviceGetPowerUsage(device,ct.byref(power))==0
        status=lib.nvmlDeviceGetTotalEnergyConsumption(device,ct.byref(energy))
        end=time.monotonic()
        return dict(t_seconds=(begin+end)/2-start,power_mw=power.value,energy_mj=energy.value if status==0 else None,
                    energy_status=status,read_seconds=end-begin)
    def measure(command=None,seconds=0):
        active=subprocess.check_output(['nvidia-smi','-i','0','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True)
        assert not active.strip(),'GPU0 must have no unrelated compute process before measurement'
        start=time.monotonic();observations=[sample(start)];stop=threading.Event()
        def monitor():
            while not stop.wait(.1):observations.append(sample(start))
        worker=threading.Thread(target=monitor);worker.start();code=0;last=''
        try:
            if command:
                log=build/'energy-process.log'
                with log.open('w') as output:
                    process=subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
                    try:code=process.wait(timeout=900)
                    except subprocess.TimeoutExpired:
                        assert os.getpgid(process.pid)==process.pid
                        os.killpg(process.pid,signal.SIGKILL);process.wait();code=124
                lines=log.read_text(errors='replace').splitlines();last=lines[-1] if lines else ''
            else:stop.wait(seconds)
        finally:stop.set();worker.join()
        observations.append(sample(start));observations.sort(key=lambda x:x['t_seconds'])
        duration=observations[-1]['t_seconds']-observations[0]['t_seconds']
        integral=sum((b['t_seconds']-a['t_seconds'])*(a['power_mw']+b['power_mw'])/2000 for a,b in zip(observations,observations[1:]))
        first,last_energy=observations[0]['energy_mj'],observations[-1]['energy_mj']
        counter=(last_energy-first)/1000 if first is not None and last_energy is not None else None
        assert counter is None or counter>=0
        return dict(exit_code=code,last_line=last,observed_seconds=duration,power_integral_joules=integral,
                    gpu_counter_joules=counter,maximum_sample_gap_seconds=max(b['t_seconds']-a['t_seconds'] for a,b in zip(observations,observations[1:])),
                    samples=observations)
    idle=measure(seconds=10)
    counters=subprocess.run(['find','-L','/sys/class/powercap','/sys/class/hwmon','-maxdepth','4','-type','f','(','-name','energy_uj','-o','-name','energy*_input',')','-readable'],capture_output=True,text=True)
    inventory=subprocess.check_output(['nvidia-smi','--query-gpu=index,name,memory.total,memory.used','--format=csv,noheader,nounits'],text=True).splitlines()
    other=subprocess.check_output(['nvidia-smi','-i','1','--query-compute-apps=used_memory','--format=csv,noheader,nounits'],text=True).splitlines()
    for seed in (20261112,20261212):
        modes=['baseline','square_alias'] if seed==20261112 else ['square_alias','baseline']
        for mode in modes:
            binary=build/f'requant_bootstrap_{mode}';expected=reference['binary_sha256']['bootstrap'][mode]
            assert hashlib.sha256(binary.read_bytes()).hexdigest()==expected
            destination=build/f'energy-{seed}-{mode}.json';value=measure([str(binary.resolve()),str(seed),str(destination.resolve())])
            if value['exit_code']==0:
                native=json.loads(destination.read_text());assert native['seed']==seed and len(native['cases'])==4
                assert all(c['max_absolute_error']<=.001 for c in native['cases'])
                value['native_result']=native
            value.update(seed=seed,variant=mode,binary_sha256=expected);cases.append(value)
            record=dict(gpu_name=name.value.decode(),idle_probe=idle,cases=cases,nominal_sample_interval_seconds=.1,
                        inventory=inventory,secondary_gpu_compute_process_count=len(other),
                        readable_cpu_energy_counter_files=counters.stdout.splitlines(),
                        source_sha256={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ('energy_study.py','integration_study.py','native/bootstrap_study.cpp')},
                        result_sha256={integration.name:hashlib.sha256(integration.read_bytes()).hexdigest()},
                        scope='Read-only NVML GPU0 power(mW) and cumulative energy(mJ);counter difference primary when supported, trapezoidal power integral retained separately. Gross GPU-reported energy across complete native process including setup and all5warm/30samples for4patterns;not host/system energy,not energy of only steady-state bootstrap,not a wattmeter calibration. Two seeds/order reversal only,not30independent energy observations. Idle probe is context,not silently subtracted. Every native slot/accuracy check retained;unchanged binary identities. GPU1 remains occupied by unrelated services and is not benchmarked;no clock/power setting changed.')
            Path('results/energy-study.json').write_text(json.dumps(record,indent=2)+'\n')
            print(seed,mode,'exit',value['exit_code'],'GPU joules',value['gpu_counter_joules'],'power integral',round(value['power_integral_joules'],2),flush=True)
            assert value['exit_code']==0,value['last_line']
    assert lib.nvmlShutdown()==0


if __name__=='__main__':main()
