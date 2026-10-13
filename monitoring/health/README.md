# Health / Monitoring Configuration

The actual liveness/readiness HTTP endpoints are implemented in
`core/health/views.py` (application code) and mounted at `/health/live`
and `/health/ready` via `config/urls/__init__.py`.

This directory holds *external monitoring configuration* that targets
those endpoints (uptime-check definitions, synthetic-monitor configs)
as it is added -- kept separate from the endpoint implementation itself
so ops/SRE configuration changes don't require a Django code change.

Empty at foundation stage.
