# prox-agent

On-demand analysis for RS Hub. Reads authenticated telemetry from the homepage backend; it does not continuously scan or automatically publish services.

API (shared `X-Service-Token`, private Docker network): GET /api/health, /api/events, /api/diagnostics, /api/rankings; POST /api/analyze-stack. /healthz is process liveness only. Backend proxy limits analysis to administrators.

Set RS_SERVICE_TOKEN (same random 32+ character secret as homepage), HOMELAB_API_URL, DOMAIN, GEMINI_API_KEYS, GEMINI_PRIMARY_MODEL and optional GEMINI_FALLBACK_MODELS through runtime .env. Credentials are excluded from images. No host port is published.

Compose parsing is local. Only a sanitized service label is sent for metadata suggestions; environment values, commands, volumes and full Compose are never sent. Diagnostic AI receives categories and severities only. Output is advisory and schema constrained. Provider failures retain local metadata/checks. Keys and raw provider errors are never returned.

Rankings show current telemetry, not 24-hour aggregates. Routes are inventory, not measured traffic. Events map Proxmox tasks deterministically. Diagnostics distinguish unavailable telemetry, healthy implemented checks and unstable workloads; deliberately exited services are not assumed broken.

Analyze accepts compose_yaml, stack_name, lxc_id, optional host_ip, service_name and published_port. Ambiguous/unresolved ports require selecting or resolving the intended published TCP mapping. It returns a manifest preview; it does not write files, deploy Compose or publish a route. Publish through the homepage's validated job flow. DNS availability is authoritative only at publication.

Run `docker compose up -d --build`; health is independent of provider quota. Run tests with `python -m unittest discover -s tests` after installing requirements.lock.
