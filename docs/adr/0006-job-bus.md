# ADR-0006: Pub/Sub job bus with an inline fallback
- **Status:** Accepted
- **Context:** Analysis takes seconds to tens of seconds. The hackathon suggests Pub/Sub, but local development and demo resilience need a no-infrastructure path.
- **Decision:** A `JobBus` interface with `PubSubJobBus` (push to the worker on Cloud Run, OIDC-verified) and `InlineJobBus` (in-process background task), selected by `JOB_BACKEND`. Jobs are idempotent and checkpointed in `jobs/{id}`.
- **Consequences:** The same handler code runs on both paths, and the demo can switch to inline if Pub/Sub misbehaves.
