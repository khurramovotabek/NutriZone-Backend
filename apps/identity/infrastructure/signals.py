"""
Django signal receivers -- framework-level housekeeping ONLY, per the
explicit, repeated prohibition in Django Implementation Blueprint
§4/§16 and MIC §4/§9: a signal receiver here must never encode a
business consequence (e.g. "when a user registers, send a welcome
notification" belongs in application/services/auth.py::VerifyOTP,
staged through the Outbox, never here).

No housekeeping signal is currently needed: BaseModel/SoftDeleteModel's
`updated_at`/`version` maintenance is already handled by
common/models/base.py's own save() override, not a signal. This file
exists (per the Universal Module Implementation Contract's mandatory
folder structure, §2.1) as an explicit, empty, documented placeholder
rather than being omitted -- so a future contributor sees a stated
"nothing belongs here yet, and here's why" rather than an unexplained
gap.
"""
