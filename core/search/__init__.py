"""
Postgres full-text-search helpers and the future search-engine adapter
seam (Enterprise Database Blueprint §15, REST API Blueprint §16).

Empty at foundation stage -- populated when the `search` bounded-context
module is implemented (Domain Architecture Specification §2.16). This
package exists now so `search`'s infrastructure layer has a stable,
pre-agreed location to add its Postgres-FTS-today /
OpenSearch-tomorrow adapter without a later restructuring.
"""
