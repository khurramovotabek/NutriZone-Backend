# 2. Use PostGIS for geo-aware columns

Date: foundation phase

## Status

Accepted

## Context

The Enterprise Database Blueprint (§4.5, §4.7, §8) specifies GIST
indexes over `geography(Point)`/`geography(Polygon)` columns for
`stores.store_locations` and `fulfillment.delivery_zones`, required for
nearest-store lookups and delivery-zone containment queries.

## Decision

The development and production PostgreSQL images are `postgis/postgis:
16-3.4` rather than the plain `postgres:16` image, so the PostGIS
extension is available from the first migration onward rather than
retrofitted when `stores`/`fulfillment` are implemented.

## Consequences

No code or migration changes are needed later to add PostGIS -- `CREATE
EXTENSION IF NOT EXISTS postgis;` can be run in the first migration that
needs it. The image is marginally larger than plain `postgres:16`; this
is an accepted tradeoff given the alternative (migrating a running
production database to a PostGIS-enabled image later) is materially
more disruptive.
