# VGen -- Video Creative Generation Platform

Campaign-based video generation platform where marketing managers upload intro hooks and main videos, define quality parameters, and the system produces all combinations at scale -- 50+ merged videos per minute per user, designed for 100K DAU.

## Architecture

```
                              React + TypeScript (Cloud Run / CDN)
                              Campaign Builder | Upload | Results
                                         |
                                         v
                              Cloud Run (API Service)
                              FastAPI -- campaigns, signed URLs, status
                                         |
                         +---------------+---------------+
                         |                               |
                         v                               v
                    Firestore                     Pub/Sub Topic
                    campaigns                     "merge-tasks"
                    videos                        1 msg per combination
                    combinations                       |
                         ^                             v
                         |                    Cloud Run (Workers)
                         |                    FFmpeg merge, 1 per instance
                         |                    autoscale 1 -> 100 (pull subscriber)
                         |                             |
                         +-------- status updates -----+
                                                       |
                                                       v
                                              Cloud Storage (GCS)
                                     /uploads/{user}/intros/
                                     /uploads/{user}/mains/
                                     /outputs/{campaign}/
                                              |
                                              v
                                     Signed download URLs
                                     served to frontend
```

**Key flow:** Browser uploads video files directly to GCS via signed URLs (API never touches video bytes). API fans out N x M combinations to Pub/Sub. Workers pull messages, download from GCS, merge with FFmpeg, upload result to GCS, update Firestore. Frontend polls campaign progress and serves download links.

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Frontend | React 18, TypeScript, Vite, TailwindCSS | Fast dev, strong typing, team familiarity |
| API | Python 3.11, FastAPI, uvicorn | Async-capable, auto-docs, Pydantic validation |
| Video processing | FFmpeg (system binary) | Industry standard, concat demuxer for lossless merge |
| Job state | Firestore (Native mode) | Serverless, real-time listeners for progress, auto-scales |
| Message queue | Pub/Sub | Unlimited fan-out (vs Cloud Tasks' 500/sec cap), dead-letter support |
| Storage | Cloud Storage (GCS) | No rate limits (vs Drive's 12K req/100s), signed URLs for direct upload/download |
| Compute | Cloud Run (3 services: frontend, API, worker) | API/frontend scale to zero; worker min 1 instance (pull subscriber), max 100 |
| Observability | structlog + Cloud Logging, Cloud Monitoring | Structured JSON logs, custom metric dashboards |
| IaC | Terraform | Reproducible, version-controlled infrastructure |
| Container | Docker (python:3.11-slim + ffmpeg) | Consistent environments, non-root user |

## Data Model (Firestore)

### Collection: `campaigns`

```
{
  id:                    string     // UUID
  user_id:               string     // authenticated user ID
  name:                  string     // "Q2 Product Launch"
  status:                string     // draft | processing | completed | failed
  quality: {
    codec:               string     // "copy" (lossless) | "h264" | "h265"
    resolution:          string     // "original" | "1920x1080" | "1280x720"
    crf:                 int        // 18-28, only if codec != "copy"
    audio_bitrate:       string     // "192k" | "128k" | "original"
  }
  total_combinations:    int        // intros.length * mains.length
  completed_count:       int        // incremented by workers
  failed_count:          int
  created_at:            timestamp
  completed_at:          timestamp | null
}
```

### Collection: `videos`

```
{
  id:                    string     // UUID
  campaign_id:           string     // FK to campaigns
  user_id:               string
  type:                  string     // "intro" | "main"
  filename:              string     // original filename
  gcs_path:              string     // "uploads/{user_id}/intros/{id}.mp4"
  size_bytes:            int
  duration_seconds:      float
  codec:                 string     // detected by ffprobe after upload
  width:                 int
  height:                int
  uploaded_at:           timestamp
}
```

### Collection: `combinations`

```
{
  id:                    string     // UUID
  campaign_id:           string     // FK to campaigns
  intro_video_id:        string     // FK to videos
  main_video_id:         string     // FK to videos
  status:                string     // pending | processing | completed | failed
  output_gcs_path:       string     // "outputs/{campaign_id}/{id}.mp4"
  output_size_bytes:     int | null
  output_duration:       float | null
  error:                 string | null
  attempts:              int        // retry counter
  started_at:            timestamp | null
  completed_at:          timestamp | null
}
```

## API Contracts

### Campaigns

| Method | Path | Request | Response |
|--------|------|---------|----------|
| POST | `/api/campaigns` | `{name, quality}` | `{id, name, status: "draft", quality}` |
| GET | `/api/campaigns` | -- | `[{id, name, status, total_combinations, completed_count, created_at}]` |
| GET | `/api/campaigns/{id}` | -- | Full campaign + progress stats |
| POST | `/api/campaigns/{id}/start` | -- | `{status: "processing", total_combinations}` |
| DELETE | `/api/campaigns/{id}` | -- | `204` |

### Uploads

| Method | Path | Request | Response |
|--------|------|---------|----------|
| POST | `/api/upload/signed-url` | `{campaign_id, type, filename, content_type}` | `{upload_url, video_id, gcs_path}` |
| POST | `/api/campaigns/{id}/videos` | `{video_id}` | `{id, type, filename, duration, codec, width, height}` |
| GET | `/api/campaigns/{id}/videos` | `?type=intro\|main` (optional) | `[{id, type, filename, gcs_path, duration_seconds, codec, width, height}]` |

**Upload flow:**
1. Frontend calls `POST /api/upload/signed-url` to get a signed GCS upload URL
2. Frontend uploads the file directly to GCS (PUT to signed URL)
3. Frontend calls `POST /api/campaigns/{id}/videos` to register the uploaded file
4. Backend runs ffprobe on the GCS object to extract metadata

### Results

| Method | Path | Request | Response |
|--------|------|---------|----------|
| GET | `/api/campaigns/{id}/results` | `?status=completed` | `[{id, intro_name, main_name, status, output_size_bytes, duration_seconds, download_url}]` |
| GET | `/api/download/{combination_id}` | -- | `{download_url}` (signed GCS URL, 1hr expiry) |
| POST | `/api/campaigns/{id}/download-all` | -- | **Not yet implemented.** Planned: `{archive_url}` (zip of all completed outputs) |

### System

| Method | Path | Response |
|--------|------|----------|
| GET | `/api/health` | `{status, version, timestamp}` |

## Frontend Pages

### 1. Dashboard (`/`)
- List of user's campaigns with status badges (draft, processing, completed)
- Progress bars for active campaigns (completed_count / total_combinations)
- "New Campaign" button

### 2. Campaign Builder (`/campaigns/new`)
- Campaign name input
- Quality settings: codec selector (copy/h264/h265), resolution (original/1080p/720p), CRF slider (shown when codec != "copy")
- Creates campaign and redirects to Campaign Detail for uploads

### 3. Campaign Detail (`/campaigns/{id}`)
- **Draft state:** upload sections for intro and main videos (file input, progress bars)
- Video list with duration and metadata per uploaded file
- Combination preview (N intros x M mains = total)
- **Launch button** -- triggers `POST /api/campaigns/{id}/start`
- **Processing state:** real-time progress via polling (3s interval)
- **Completed state:** results table with status, size, duration, individual download links

## Worker Pipeline

Each worker instance processes **one video at a time** (Cloud Run `max_instance_request_concurrency = 1`).

```
1. Pull Pub/Sub message
   {combination_id, campaign_id, intro_gcs_path, main_gcs_path, quality}

2. Idempotency check: if combination.status == "completed", skip (Pub/Sub at-least-once)

3. Update Firestore: combination.status = "processing"

4. Download intro + main from GCS to /tmp
   (direct GCS client, no rate limits, ~2-5s per file)

5. Check compatibility (ffprobe: codec, resolution, fps, audio)
   Compatible + quality.codec == "copy"  --> stream-copy (fast)
   Incompatible or re-encode requested   --> ffmpeg concat with re-encode

6. Merge with FFmpeg
   Stream-copy: ~2s for typical 30s videos
   Re-encode:   ~30-60s depending on resolution/length

7. Validate output (ffprobe: duration, size, codec)

8. Upload result to GCS: outputs/{campaign_id}/{combination_id}.mp4

9. Update Firestore:
   - combination.status = "completed"
   - combination.output_gcs_path, output_size_bytes, output_duration
   - campaign.completed_count += 1 (atomic increment)

10. If all combinations done: campaign.status = "completed"

11. Always ack Pub/Sub message (even on failure -- prevents infinite redelivery)

On failure:
   - combination.status = "failed", error = message
   - campaign.failed_count += 1
   - Message is acked; failed combinations tracked in Firestore
   - Retries should be handled at the application level

12. Cleanup: shutil.rmtree(/tmp/workdir)
```

## Scale Design

### Why Pub/Sub over Cloud Tasks

| | Cloud Tasks | Pub/Sub |
|---|---|---|
| Max dispatch rate | 500/sec/queue | Unlimited (1M+ msg/sec) |
| Fan-out | Sequential dispatch | Instant publish |
| Dead-letter | No | Built-in DLQ topic |
| Backlog visibility | Limited | Full metrics |
| Cost at scale | Higher (per-task pricing) | Lower ($40/TB) |

A campaign with 50 combinations needs 50 messages published instantly. At 100K DAU with overlapping campaigns, peak message rate can hit thousands/second. Cloud Tasks caps at 500.

### Why GCS over Google Drive

| | Google Drive | Cloud Storage |
|---|---|---|
| API rate limit | 12,000 req / 100s / project | Practically unlimited |
| Upload method | API proxy (bytes through server) | Signed URLs (direct browser-to-storage) |
| Download speed | Throttled | Full bandwidth |
| Cost | Free (with limits) | $0.02/GB/month |
| Auth model | OAuth / service account sharing | IAM + signed URLs |

At 100K DAU, Drive's rate limit would be hit within seconds. GCS signed URLs bypass the API entirely -- uploads and downloads go directly between the browser and storage.

### Throughput math

```
Assumptions:
  - Average video: 30s, 50MB
  - Stream-copy merge: ~2s on 2 vCPU
  - GCS download: ~1s per file (within GCP network)
  - GCS upload: ~2s per file
  - Total per merge: ~7s wall-clock

Per user (50 combinations):
  - Pub/Sub fan-out: instant
  - 50 workers in parallel: all 50 complete in ~7s
  - Throughput: 50 videos in <10s = 300+ videos/min

Peak load (1,000 concurrent campaigns x 50 combos):
  - 50,000 merges needed
  - Cloud Run autoscales to hundreds of worker instances
  - Each instance: 1 merge at a time, ~7s each
  - 500 instances = ~4,200 merges/min
  - Clear 50,000 backlog in ~12 minutes

Cost per 1,000 merges (stream-copy):
  - Cloud Run: 1,000 x 7s x 2 vCPU = 14,000 vCPU-sec = ~$0.34
  - GCS operations: ~$0.01
  - Pub/Sub: negligible
  - Total: ~$0.35 per 1,000 videos
```

## Project Structure

```
frontend/
  src/
    components/           # Reusable UI components
    pages/                # Dashboard, CampaignBuilder, CampaignDetail
    hooks/                # useUpload
    api/                  # API client (fetch wrapper, types)
    types/                # TypeScript interfaces
  public/
  index.html              # Loads runtime API URL via window.__VITE_API_URL__
  nginx.conf
  docker-entrypoint.sh    # Injects VITE_API_URL at container start
  Dockerfile.dev
  vite.config.ts
  tsconfig.json
  package.json

src/                      # Backend
  config.py               # Pydantic-settings, env-based config
  api/
    main.py               # FastAPI app + lifespan
    routes/
      campaigns.py        # Campaign CRUD + start
      uploads.py          # Signed URL generation + video registration
      results.py          # Download URLs + results listing
      health.py           # Health check
  jobs/
    store.py              # Firestore-backed state management
  storage/
    client.py             # GCS client + signed URL generation
  video/
    merger.py             # FFmpeg concat + re-encode
    validator.py          # ffprobe validation + compatibility check
  worker/
    consumer.py           # Pub/Sub pull subscription handler
    pipeline.py           # Download -> merge -> upload -> update pipeline
  pubsub/
    publisher.py          # Fan-out: publish N*M messages
  observability/
    logging.py            # structlog + Cloud Logging
    metrics.py            # Cloud Monitoring custom metrics

infrastructure/
  providers.tf
  variables.tf
  main.tf                 # All GCP resources
  cicd.tf                 # Artifact Registry, Cloud Build trigger, IAM
  outputs.tf

cloudbuild.yaml           # CI/CD pipeline (build, push, deploy)
Dockerfile                # Backend (API + worker, same image)
Dockerfile.frontend       # Frontend (nginx or Cloud Run)
docker-compose.yml        # Local dev: frontend + API + worker + emulators
```

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GCP_PROJECT_ID` | yes | -- | GCP project ID |
| `GCS_UPLOAD_BUCKET` | yes | -- | Bucket for user uploads |
| `GCS_OUTPUT_BUCKET` | yes | -- | Bucket for merged outputs |
| `PUBSUB_TOPIC` | no | `merge-tasks` | Pub/Sub topic for merge jobs |
| `PUBSUB_SUBSCRIPTION` | no | `merge-tasks-sub` | Worker subscription |
| `PUBSUB_DLQ_TOPIC` | no | `merge-tasks-dlq` | Dead-letter topic |
| `FIRESTORE_COLLECTION_PREFIX` | no | `""` | Prefix for collection names (for namespacing) |
| `WORKER_MAX_RETRIES` | no | `5` | Max Pub/Sub delivery attempts |
| `SIGNED_URL_EXPIRY_MINUTES` | no | `60` | Signed URL expiration |
| `GCP_REGION` | no | `us-central1` | GCP region |
| `CORS_ORIGINS` | no | `["*"]` | Allowed CORS origins (JSON list) |
| `APP_VERSION` | no | `1.0.0` | Version string returned by health endpoint |
| `LOG_LEVEL` | no | `INFO` | Python log level |
| `VITE_API_URL` | yes | -- | API URL for frontend (runtime, injected at container start) |

## Terraform Resources

| Resource | Type | Purpose |
|----------|------|---------|
| `google_project_service.apis` | API enablement | run, pubsub, firestore, storage, monitoring, logging, iam, artifactregistry, cloudbuild |
| `google_firestore_database.default` | Firestore | Native mode, job + campaign state |
| `google_service_account.api` | IAM | API service identity |
| `google_service_account.worker` | IAM | Worker service identity |
| `google_storage_bucket.uploads` | GCS | User-uploaded source videos |
| `google_storage_bucket.outputs` | GCS | Merged output videos |
| `google_pubsub_topic.merge_tasks` | Pub/Sub | Merge job messages |
| `google_pubsub_subscription.worker` | Pub/Sub | Pull subscription for worker (ack 600s, 5 retries, DLQ) |
| `google_pubsub_topic.dlq` | Pub/Sub | Dead-letter for failed merges |
| `google_cloud_run_v2_service.frontend` | Cloud Run | React app (nginx) |
| `google_cloud_run_v2_service.api` | Cloud Run | FastAPI, 2 CPU / 2Gi |
| `google_cloud_run_v2_service.worker` | Cloud Run | FFmpeg worker, 4 CPU / 8Gi, concurrency=1, min 1 instance |
| `google_monitoring_dashboard.vgen` | Monitoring | Campaigns, throughput, errors, queue depth |
| `google_artifact_registry_repository.vgen` | Artifact Registry | Docker image storage |
| `google_cloudbuild_trigger.deploy_on_push` | Cloud Build | Auto-deploy on push to main |

## CI/CD

Automated via **Cloud Build**, triggered on every push to `main` on GitHub.

```
push to main
    |
    +-- build-backend ----+-- push-backend --+-- deploy vgen-api -----+
    |      (parallel)     |    (parallel)    +-- deploy vgen-worker ---+
    +-- build-frontend ---+-- push-frontend -+-- deploy vgen-frontend +
```

**Pipeline (`cloudbuild.yaml`):**
- Builds backend and frontend Docker images in parallel
- Pushes to Artifact Registry (tagged `$SHORT_SHA` + `latest`)
- Deploys all 3 Cloud Run services in parallel
- Uses `E2_HIGHCPU_8` machine, 20 min timeout

**Images:**
- `us-central1-docker.pkg.dev/{project}/vgen/backend:{sha}` -- API + worker
- `us-central1-docker.pkg.dev/{project}/vgen/frontend:{sha}` -- React app (nginx)

**IAM:** Cloud Build SA gets `roles/run.admin`, `roles/iam.serviceAccountUser`, `roles/artifactregistry.writer`.

**Setup requirement:** GitHub repo must be connected to Cloud Build manually once via Console: **Cloud Build > Triggers > Connect Repository > GitHub**. After that, the Terraform trigger handles the rest.

## Key Design Decisions

1. **Signed URLs for upload/download** -- API never touches video bytes. Browser uploads directly to GCS, downloads directly from GCS. Eliminates API as bottleneck.

2. **Pub/Sub over Cloud Tasks** -- instant fan-out for N*M combinations, built-in dead-letter queue, no dispatch rate cap. Critical for scale.

3. **GCS over Google Drive** -- Drive API rate limits (12K req/100s) would be exhausted instantly at 100K DAU. GCS has no practical limit and is cheaper.

4. **Worker concurrency = 1, min 1 instance** -- video merging is CPU-bound. One merge per instance, Cloud Run autoscales instances. Min 1 instance required because the worker is a Pub/Sub pull subscriber -- Cloud Run would otherwise scale to zero (no incoming HTTP requests) and never process messages.

5. **Stream-copy when possible** -- if intro and main share codec + resolution, FFmpeg concat demuxer copies streams without re-encoding (~50x faster). Fall back to re-encode only when necessary or when user selects specific quality.

6. **Campaign as unit of work** -- groups all combinations for a user's batch. Enables progress tracking, batch download, and retry at campaign level.

7. **Atomic Firestore increments** -- `completed_count` and `failed_count` use `firestore.Increment()` to avoid race conditions across parallel workers.

8. **Dead-letter topic** -- after max retries, failed messages land in DLQ for manual inspection. No silent data loss.

9. **Same Docker image for API and worker** -- reduces build complexity. Different Cloud Run configs (CPU, memory, concurrency) differentiate them.

10. **Frontend on Cloud Run** -- serves static build via nginx. Could move to Cloud CDN + GCS static hosting for lower cost at scale.

11. **Runtime API URL injection** -- `VITE_API_URL` is injected at container start via `docker-entrypoint.sh` which writes `window.__VITE_API_URL__` into `index.html`. The frontend client reads this at runtime. This avoids rebuilding the frontend when the API URL changes and solves the chicken-and-egg problem where the API URL isn't known at build time.

12. **Idempotent message processing** -- workers check combination status before processing. If already completed, the message is skipped and acked. This handles Pub/Sub's at-least-once delivery guarantee without corrupting state.

## Sandbox Environment

| Resource | Value |
|----------|-------|
| GCP Project | `sandbox-456317` |
| Region | `us-central1` |
| GCS Uploads | `sandbox-456317-vgen-uploads` |
| GCS Outputs | `sandbox-456317-vgen-outputs` |
| Pub/Sub Topic | `merge-tasks` |
| Pub/Sub Subscription | `merge-tasks-sub` (ack 600s, 5 retries, DLQ) |
| Pub/Sub DLQ | `merge-tasks-dlq` |
| Firestore | `(default)` native mode |
| Artifact Registry | `us-central1-docker.pkg.dev/sandbox-456317/vgen` |
| Terraform State | `gs://sandbox-456317-tf-state/vgen` |
| GCP Account | `sandbox1@zimran.io` |
| Frontend URL | `https://vgen-frontend-kuvjowj3aq-uc.a.run.app` |
| API URL | `https://vgen-api-kuvjowj3aq-uc.a.run.app` |
| Cloud Build Trigger | `vgen-deploy-on-push` (push to main) |
| GitHub Repo | `topcoderkz/zimran-vgen` |
