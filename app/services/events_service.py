import datetime as dt
import hashlib
import json
from app.services.telemetry import telemetry

class EventsService:
    async def get_major_events(self, limit=30):
        status=await telemetry.get()
        results=[]
        for task in status.get("backups",{}).get("tasks",[])[:limit]:
            state=task.get("status","running")
            title=task.get("description") or task.get("type") or "Proxmox task"
            identity=json.dumps([task.get("start"),task.get("type"),task.get("target"),task.get("user")])
            results.append({"id":hashlib.sha256(identity.encode()).hexdigest()[:20],"timestamp":dt.datetime.fromtimestamp(float(task.get("start",0)),dt.timezone.utc).isoformat(),"type":"backup" if task.get("type")=="vzdump" else "system","severity":"success" if state=="OK" else "info" if state=="running" or not task.get("end") else "error","title":title,"summary":f"{title}: {state}; target {task.get('target','unknown')}.","target":str(task.get("target","pve")),"source":"Proxmox task inventory"})
        return results
events_service=EventsService()
