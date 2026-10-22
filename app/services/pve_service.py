import hashlib
import ipaddress
import json
import re
import tomllib
from typing import Literal
import yaml
from pydantic import BaseModel, ConfigDict, Field
from app.config import config
from app.gemini_client import gemini
from app.services.telemetry import telemetry, cache

LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
SECRET = re.compile(r"password|passwd|secret|token|api.?key|credential|private.?key", re.I)

class Metadata(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(max_length=100)
    type: Literal["multimedia", "tools", "networking", "infrastructure", "misc"] = "misc"
    description: str = Field(default="", max_length=80)
    icon: Literal["Music", "Radio", "Tv", "Film", "Cloud", "Code", "HardDrive", "Network", "Globe", "Server", "ShieldCheck", "Activity", "Database", "Terminal", "Box", "Wrench"] = "Box"
    color: str = Field(default="#96c2e2", pattern=r"^#[a-fA-F0-9]{6}$")
    suggested_subdomains: list[str] = Field(default_factory=list, max_length=4)

def parse_compose(text):
    if len(text)>60000 or len(re.findall(r"[&*][A-Za-z0-9]",text))>30:
        raise ValueError("Compose input is too large or contains too many aliases")
    data = yaml.safe_load(text)
    if not isinstance(data,dict) or not isinstance(data.get("services"),dict) or not data["services"]:
        raise ValueError("Compose must define services")
    # Only service names and sanitized image identifiers may leave this process.
    # No environment, command, labels, URLs, volumes or arbitrary YAML reaches AI.
    options = []
    for name, service in data["services"].items():
        if not isinstance(service,dict):
            raise ValueError("Invalid Compose service")
        for entry in service.get("ports",[]) or []:
            protocol = "tcp"
            published = None
            if isinstance(entry,dict):
                protocol = entry.get("protocol","tcp")
                published = entry.get("published")
            elif isinstance(entry,(str,int)):
                raw = str(entry)
                if "/" in raw:
                    raw, protocol = raw.rsplit("/",1)
                # Last two components are host and container port, including IPv6 bind forms.
                parts = raw.rsplit(":",2)
                if len(parts)>=2:
                    published = parts[-2]
            if protocol != "tcp" or published is None:
                continue
            if not str(published).isdigit():
                continue
            port = int(published)
            if not 1<=port<=65535:
                raise ValueError("Published port out of range")
            options.append({"service":str(name), "port":port, "container":service.get("container_name", "")})
    return data, options

def manifest(metadata, public_url, container):
    fields = {"runtime":"docker", "name":metadata.name, "type":metadata.type, "description":metadata.description, "url":public_url,"icon":metadata.icon,"color":metadata.color,"check_url":public_url}
    if container:
        fields["container"] = container
    result = "[service]\n" + "".join(f"{k} = {json.dumps(v, ensure_ascii=False)}\n" for k,v in fields.items()) + "enabled = true\n"
    tomllib.loads(result)
    return result

class PveService:
    async def analyze_and_generate(self, compose_yaml, stack_name, lxc_id=100, host_ip=None, create_route=True, service_name=None, published_port=None):
        if not LABEL.fullmatch(stack_name):
            raise ValueError("Stack name must be a valid lowercase DNS label")
        data, options = parse_compose(compose_yaml)
        if service_name:
            options=[o for o in options if o["service"]==service_name]
        if published_port is not None:
            options=[o for o in options if o["port"]==published_port]
        if len(options)!=1:
            raise ValueError("Choose exactly one published TCP service/port; dynamic ports, ranges and unresolved variables need explicit resolved Compose. Candidates: "+json.dumps(options))
        chosen=options[0]
        status=await telemetry.get()
        lxc=next((l for l in status["lxcs"] if l["id"]==lxc_id),None)
        if lxc is None:
            raise ValueError("Unknown LXC")
        origin=host_ip or ("127.0.0.1" if lxc_id==101 else lxc.get("ip"))
        try:
            address=ipaddress.ip_address(origin)
        except ValueError:
            raise ValueError("Supply the selected LXC's reachable origin IP") from None
        if address.is_multicast or address.is_unspecified or address.is_link_local or (address.is_loopback and lxc_id!=101):
            raise ValueError("Origin must be reachable from the Debian tunnel host")
        occupied={r["name"].lower() for r in status.get("routes",[])} | {"home","prox","pve"}
        # Use a narrow allowlist for external model input; redact arbitrary user values.
        safe_name=stack_name if not SECRET.search(stack_name) else "service"
        key=hashlib.sha256(safe_name.encode()).hexdigest()
        async def generate():
            fallback=Metadata(name=stack_name.title(),description="Homelab service",suggested_subdomains=[stack_name])
            try:
                response=await gemini.generate_json("Suggest service metadata for this service name: "+json.dumps(safe_name)+". Return name,type,description,icon,color,suggested_subdomains only.", "Return a JSON object. Allowed type: multimedia,tools,networking,infrastructure,misc; icon: Box,Server,Cloud,Music,Code; color: hex #RRGGBB. Description max 80 characters.")
                return Metadata.model_validate(response["data"]),response["model"]
            except Exception:
                return fallback,"local"
        meta,model=await cache.get("compose:"+key,generate)
        candidates=[c for c in meta.suggested_subdomains if LABEL.fullmatch(c) and c not in occupied]
        for suffix in ("", "-app", "-2", "-3"):
            candidate=stack_name[:63-len(suffix)]+suffix
            if candidate not in occupied and candidate not in candidates:
                candidates.append(candidate)
        if not candidates:
            raise ValueError("No unoccupied route label available")
        selected=candidates[0]
        domain=status.get("domain") or config.DOMAIN
        url=f"https://{selected}.{domain}"
        container=chosen["container"]
        if not container:
            containers=lxc.get("containers",[])
            matches=[c["name"] for c in containers if c["name"] in (f"{stack_name}-{chosen['service']}-1",f"{stack_name}_{chosen['service']}_1")]
            container=matches[0] if len(matches)==1 else ""
        return {"stack_name":stack_name,"chosen_subdomain":selected,"subdomain_candidates":candidates,"public_url":url,"domain":domain,"port":chosen["port"],"scheme":"http","pve_toml":manifest(meta,url,container),"parsed_metadata":meta.model_dump(),"route_action_payload":{"action":"create_route","name":selected,"host":str(address),"port":chosen["port"],"scheme":"http"} if create_route else None,"origin_host":str(address),"ai_model_used":model,"availability":"No existing configured route; DNS conflict checked only during publication","manifest_saved":False,"lxc_name":lxc.get("name"),"lxc_id":lxc_id}
pve_service=PveService()
