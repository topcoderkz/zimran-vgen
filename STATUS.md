# VGen -- Project Status

Last updated: 2026-04-23

## Feature Status

### DONE

| Feature | Notes |
|---------|-------|
| Dashboard page | Lists campaigns with status badges, progress bars, new campaign button |
| Campaign CRUD API | Create, list, get, delete -- all endpoints working |
| Signed URL upload flow | Browser uploads directly to GCS via signed URLs, no bytes through API |
| Video registration + ffprobe | Backend extracts metadata (codec, resolution, fps, duration) after upload |
| Pub/Sub fan-out | N intros x M mains = N*M messages published instantly |
| Worker merge (stream-copy) | Lossless concat when intro/main are compatible (~2s per merge) |
| Compatibility check | ffprobe validates codec, resolution, fps, audio before choosing merge strategy |
| Progress tracking | Real-time polling on Campaign Detail (3s interval), atomic Firestore increments |
| Individual download | Signed GCS URLs with 1hr expiry |
| Structured logging | structlog + Cloud Logging JSON output, all major operations logged |
| CI/CD pipeline | Cloud Build auto-deploys on push to main (backend + frontend + worker) |
| Terraform IaC | All GCP resources managed: Cloud Run, GCS, Pub/Sub, Firestore, IAM |
| Idempotent message processing | Workers skip already-completed combinations (Pub/Sub at-least-once safe) |
| Worker min-instances | Pull subscriber stays alive with min 1 Cloud Run instance |

### PARTIAL

| Feature | What works | What's missing |
|---------|-----------|----------------|
| Campaign Builder | Name + quality settings (codec, resolution, CRF) | Audio bitrate selector not exposed in UI (hardcoded to "original"). Spec called for 4-step wizard but current UX is single form + upload on detail page |
| Campaign Detail | Uploads, launch, progress, results with download | No retry button for failed combinations. No bulk download. No combination grid with per-cell status |
| Worker merge (re-encode) | FFmpeg re-encode runs when incompatible or codec != "copy" | **Quality settings ignored:** CRF hardcoded to 23, audio bitrate to 192k, resolution not scaled. User-selected values in the campaign are passed through Pub/Sub but never applied to the FFmpeg command |
| Metrics | `videos_processed`, `processing_time_ms`, `errors` sent to Cloud Monitoring | No queue depth metrics, no per-stage timing (download/merge/upload), no dashboard alerts |
| Results API | List with status filter, individual download URLs | Bulk download as zip not implemented (`POST /api/campaigns/{id}/download-all`) |

### MISSING

| Feature | Priority | Notes |
|---------|----------|-------|
| Authentication | High | All endpoints hardcoded to `user_id = "default_user"` (see `campaigns.py:37`). No JWT/OAuth middleware. Multi-user deployment is unsafe without this |
| Tests | High | `tests/` directory exists but contains only empty `__init__.py` files. No unit, integration, or e2e tests |
| Retry failed combinations | Medium | No UI or API to retry failed combinations. Workers always ack messages; retries must be application-level but no mechanism exists |
| Bulk download (zip) | Medium | API endpoint not implemented. Frontend has no bulk select UI |
| Dead-letter monitoring | Medium | DLQ topic exists in Pub/Sub but nothing consumes or alerts on it |
| Results Download page | Low | Spec called for separate `/campaigns/{id}/results` route; results shown inline on Campaign Detail instead. May not need a separate page |

## Critical Bugs

### 1. Campaign status always "completed" even with failures

**File:** `src/jobs/store.py:81`
**Status:** Fixed (2026-04-23)

Both branches of the ternary set status to `"completed"`. The else branch should be `"failed"`.

### 2. Quality settings ignored during re-encode

**File:** `src/video/merger.py:55-65`

`merge_videos_reencode()` hardcodes CRF=23, audio_bitrate=192k, and does not apply resolution scaling. The quality dict is available in the pipeline message but never passed to the merge function.

**Impact:** Users who select h264/h265 with custom CRF or resolution get default settings regardless.

## Architecture Notes

- Worker uses Pub/Sub **pull** subscription (not push). Requires `min_instance_count = 1` on Cloud Run to prevent scale-to-zero killing the subscriber.
- Messages are always acked (even on failure) to prevent infinite redelivery loops. Failed combinations are tracked in Firestore.
- Frontend API URL is injected at container runtime via `docker-entrypoint.sh` writing `window.__VITE_API_URL__`.
