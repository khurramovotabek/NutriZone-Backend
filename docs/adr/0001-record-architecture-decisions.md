# 1. Record architecture decisions

Date: foundation phase

## Status

Accepted

## Context

The NutriZone platform is governed by seven binding documents (the
Engineering Constitution, Architecture Review, Domain Architecture
Specification, Enterprise Database Blueprint, Enterprise REST API
Blueprint, Django Implementation Blueprint, and the Universal Module
Implementation Contract). Those documents are deliberately broad and
durable. Day-to-day implementation still produces smaller, local
decisions (e.g. "which Redis client library," "how do we structure the
Nginx upstream split") that don't belong in those top-level documents
but still need a durable, discoverable record.

## Decision

We will use Architecture Decision Records (ADRs), one per significant
local decision, numbered sequentially, stored in `docs/adr/`, using
Michael Nygard's lightweight format (Context / Decision / Consequences).

An ADR is written whenever a decision:
- Is hard to reverse, or
- Affects more than one bounded-context app, or
- Deviates from an example/default suggested by one of the seven
  binding documents (in which case the ADR must explain why, per those
  documents' own amendment-discipline requirements).

## Consequences

Future contributors can trace *why* a foundation-level choice was made
(e.g. "why PostGIS instead of a generic geo library," "why five Celery
queues instead of one per bounded context") without needing to have
been present for the discussion. ADRs are never edited after acceptance
to reflect a changed decision -- a changed decision gets a new ADR that
supersedes the old one, preserving history.
