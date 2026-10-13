"""
Django signal receivers -- framework-level housekeeping ONLY, per the
explicit, repeated prohibition in Django Implementation Blueprint
§4/§16 and MIC §4/§9 (restated here at the point of construction, per
the same reasoning `apps/identity/infrastructure/signals.py` already
documents: this is the single most-violated rule in typical Django
projects).

No housekeeping signal is currently needed here either --
`common/models/base.py`'s save() override already handles `updated_at`/
`version` maintenance without a signal. Kept as an explicit, empty,
documented placeholder rather than omitted, per the Universal Module
Implementation Contract's mandatory folder structure (§2.1).
"""
