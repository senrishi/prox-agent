# prox-agent

An intelligent Homelab AI Assistant service powered by Google Gemini AI Studio API. Built for Proxmox VE, Docker, and Cloudflare homelab architectures.

## Features

- **Docker Compose & pve.toml Auto-Generation**: Analyzes `compose.yaml` files, suggests clean and available subdomains, checks Cloudflare DNS/tunnel routes, and automatically generates valid `pve.toml` configurations.
- **Homelab Event Tracking**: Analyzes Proxmox VE tasks, container status changes, and critical lifecycle events with Gemini AI 1-sentence summaries.
- **Homelab Diagnostics & Anomaly Doctor**: Scans resource usage (high RAM/CPU thresholds, storage saturation, CPU thermals, container crash loops) and provides plain-English root causes with actionable remediation commands.
- **Performance Rankings & Leaderboards**: Computes daily 24h rankings for highest RAM consumers, CPU consumers, and Cloudflare tunnel route traffic, with rank shift indicators (▲, ▼) and executive insights.
- **Resilient AI Studio Integration**:
  - Primary model: `gemini-3.5-flash-lite` with automatic fallback to `gemini-3.1-flash-lite` and `gemini-3.5-flash`.
  - Unlimited round-robin key rotation across any number of Gemini API keys with automatic failover on quota/rate-limits.
  - Zero heavy local ML footprint: 100% lightweight Python async service consuming < 40MB RAM.

## API Endpoints

- `GET /health` - Health check and active configuration summary.
- `POST /api/compose/analyze` - Analyzes a compose file, suggests subdomains, checks availability, and generates `pve.toml`.
- `POST /api/compose/apply` - Writes `pve.toml` to service directory and triggers Cloudflare route creation.
- `GET /api/events` - Returns filtered major homelab events with Gemini summaries.
- `GET /api/diagnostics` - Returns active homelab issues, root causes, and remediation commands.
- `GET /api/rankings` - Returns RAM, CPU, and route traffic leaderboards with rank shifts and executive insights.

## Quick Start

### 1. Configuration
Create a `.env` file based on `.env.example`:
```bash
cp .env.example .env
```
Add your Google AI Studio API key(s):
```env
GEMINI_API_KEYS=key1,key2,key3
PROXMOX_HOST=192.168.1.50
CLOUDFLARE_ZONE_ID=your_zone_id
CLOUDFLARE_API_TOKEN=your_token
HOMELAB_DOMAIN=958901.xyz
```

### 2. Run with Docker Compose
```bash
docker compose up -d --build
```
The service will start listening on port `8090` attached to the `homepage-net` Docker network.
