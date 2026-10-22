import re
from app.services.telemetry import telemetry

def memory_bytes(container):
    if isinstance(container.get("memory_bytes"),(int,float)):
        return container["memory_bytes"]
    match=re.match(r"([0-9.]+)\s*([KMGT]?i?B)",container.get("memory_text", ""),re.I)
    if not match:
        return 0
    unit=match[2].lower();power={"b":0,"kb":1,"kib":1,"mb":2,"mib":2,"gb":3,"gib":3,"tb":4,"tib":4}[unit]
    return float(match[1])*(1024 if 'i' in unit else 1000)**power

class RankingsService:
    async def get_performance_rankings(self):
        status=await telemetry.get()
        containers=[]
        for lxc in status["lxcs"]:
            for c in lxc.get("containers",[]):
                containers.append({"name":c["name"],"lxc_id":lxc["id"],"lxc_name":lxc.get("name","LXC"),"memory_bytes":memory_bytes(c),"memory_text":c.get("memory_text","Unavailable"),"memory_percent":c.get("memory_percent",0),"cpu_percent":c.get("cpu",0),"state":c.get("state","unknown"),"movement":"same","delta":0})
        def ranked(field):
            return [{**c,"rank":i,"value":c[field]} for i,c in enumerate(sorted(containers,key=lambda c:c[field],reverse=True)[:10],1)]
        memory=ranked("memory_bytes");cpu=ranked("cpu_percent")
        routes=[{"rank":i,"name":r["name"],"url":r.get("url",""),"target":f"{r.get('host')}:{r.get('port')}","movement":"same","delta":0} for i,r in enumerate(status.get("routes",[]),1)]
        return {"updated":status["updated"],"window":"Current telemetry snapshot; no traffic measurements or daily aggregates","top_memory":memory,"top_cpu":cpu,"top_routes":routes,"ai_insight":"Current measurements ranked by absolute RAM and CPU usage. Routes are inventory, not traffic rankings.","analysis_mode":"local","movement_available":False}
rankings_service=RankingsService()
