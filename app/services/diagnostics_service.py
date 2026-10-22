import datetime as dt
import hashlib
import json
from app.gemini_client import gemini
from app.services.telemetry import telemetry, cache

class DiagnosticsService:
    async def run_diagnostics(self):
        status=await telemetry.get()
        anomalies=[]
        def add(component,severity,symptom,target,command):
            anomalies.append({"id":hashlib.sha256((component+str(target)).encode()).hexdigest()[:20],"severity":severity,"component":component,"summary":symptom,"evidence":symptom,"target":str(target),"suggested_fix":command,"timestamp":status["updated"],"analysis_mode":"local"})
        host=status["host"]
        temp=host.get("sensors",{}).get("cpu_package")
        if isinstance(temp,(float,int)) and temp>=78:
            add("Host CPU thermal","critical" if temp>=85 else "warning",f"Measured CPU package temperature {temp}°C.","pve","On Proxmox: inspect cooling and run sensors. Do not change thermal limits automatically.")
        for pool in host.get("storages",[]):
            if pool.get("total",0)>0 and pool.get("used",0)/pool["total"]>=0.8:
                add("Storage pool","critical" if pool["used"]/pool["total"]>=0.9 else "warning",f"Pool {pool.get('name')} is {pool['used']/pool['total']:.1%} used.",pool.get("name"),"On Proxmox: pvesm status; lvs -o lv_name,data_percent,metadata_percent. Inspect before deleting or resizing anything.")
        for lxc in status["lxcs"]:
            identity=f"{lxc.get('name','LXC')} ({lxc['id']})"
            limit=lxc.get("memory_limit",0)
            if lxc.get("state")=="running" and limit>0 and lxc.get("memory",0)/limit>=0.88:
                add(identity,"critical" if lxc["memory"]/limit>=0.95 else "warning",f"RAM is {lxc['memory']/limit:.1%} of configured limit.",identity,f"On Proxmox: pct exec {int(lxc['id'])} -- free -m. Inspect workload and host headroom before changing limits.")
            for container in lxc.get("containers",[]):
                # An exited workload may be intentionally staged; only unstable states are anomalous.
                if container.get("state") in ("restarting","dead"):
                    add("Unstable container","critical",f"{container.get('name')} in {identity} is {container.get('state')}.",identity,"Inspect logs and restart history in the affected LXC; no automatic restart is performed.")
        if not anomalies:
            return [{"id":"healthy","severity":"healthy","component":"Implemented checks","summary":"No anomalies found in the available thermal, storage, LXC memory and unstable-container checks.","suggested_fix":"No action suggested by these checks.","target":"pve","timestamp":status["updated"],"analysis_mode":"local"}]
        # Send only numeric severities/evidence categories, never arbitrary names/logs or commands.
        async def explain():
            try:
                safe=[{"id":a["id"],"component":a["component"] if a["component"] in ("Host CPU thermal","Storage pool","Unstable container") else "LXC memory","severity":a["severity"]} for a in anomalies]
                result=await gemini.generate_json("Explain possible causes for these categories. Return a JSON object mapping id to a short advisory explanation, not commands: "+json.dumps(safe),"Do not claim a root cause is verified. Maximum 400 characters per explanation.")
                raw=result["data"]
                if isinstance(raw,dict):
                    return {k:v for k,v in raw.items() if isinstance(v,str) and len(v)<=400}
            except Exception:
                pass
            return {}
        explanations=await cache.get("diagnostics:"+hashlib.sha256(json.dumps(anomalies,sort_keys=True).encode()).hexdigest(),explain)
        for a in anomalies:
            if a["id"] in explanations:
                a["summary"] += " Possible causes (AI advisory): "+explanations[a["id"]]
                a["analysis_mode"]="AI advisory with local evidence"
        return anomalies
diagnostics_service=DiagnosticsService()
