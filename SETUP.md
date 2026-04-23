# Setup Guide

Step-by-step instructions to run VGen locally and deploy to GCP. Written for engineers joining the project for the first time.

---

## Prerequisites

Install these tools before starting. Versions shown are minimum requirements.

### Node.js 18+ (frontend)

```bash
# Check
node --version   # should be 18+
npm --version

# macOS
brew install node

# Ubuntu/Debian
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# Or use nvm (recommended for version management)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
nvm install 18
nvm use 18
```

### Python 3.11+ (backend)

```bash
# Check
python3 --version

# macOS
brew install python@3.11

# Ubuntu/Debian
sudo apt update && sudo apt install python3.11 python3.11-venv
```

### FFmpeg (video processing)

```bash
# Check
ffmpeg -version

# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt update && sudo apt install ffmpeg
```

### Docker Desktop

Download from https://www.docker.com/products/docker-desktop/

```bash
# Verify
docker --version          # 24+
docker compose version    # v2+
```

### Google Cloud CLI (deployment)

```bash
# macOS
brew install google-cloud-sdk

# Or follow: https://cloud.google.com/sdk/docs/install

# Verify
gcloud --version
```

### Terraform (infrastructure)

```bash
# macOS
brew install terraform

# Verify
terraform --version   # 1.5+
```

---

## Local Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd zimran-vgen
```

### 2. Backend setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate    # macOS/Linux
# Windows: venv\Scripts\activate

# You should see (venv) at the start of your prompt

# Install Python dependencies
pip install -r requirements.txt
```

### 3. Frontend setup

```bash
cd frontend
npm install
cd ..
```

### 4. Environment files

```bash
# Backend
cp .env.example .env
# Open .env and fill in your values (see table below)

# Frontend
cp frontend/.env.example frontend/.env.local
# Set VITE_API_URL=http://localhost:8080/api
```

The `.env` file is already populated with sandbox values. If starting fresh, here are the values:

```
GCP_PROJECT_ID=sandbox-456317
GCS_UPLOAD_BUCKET=sandbox-456317-vgen-uploads
GCS_OUTPUT_BUCKET=sandbox-456317-vgen-outputs
```

For local development with Docker Compose, the Firestore/Pub/Sub emulators handle state -- you don't need GCP credentials to get started.

### 5. GCP credentials (for Cloud Storage access)

```bash
# Option A: Use Application Default Credentials (easiest for local dev)
gcloud auth application-default login

# Option B: Service account key (for Docker or CI)
# 1. Go to GCP Console > IAM > Service Accounts
# 2. Create a service account or use existing one
# 3. Create key > JSON > save as credentials.json in project root
# 4. Set in .env: GOOGLE_APPLICATION_CREDENTIALS=credentials.json
```

---

## Running Locally

### Option A: Docker Compose (recommended)

Starts everything in one command: frontend, API, worker, Firestore emulator, Pub/Sub emulator.

```bash
# Build and start all services
docker compose up --build
```

You'll see logs from all services. When ready:
- **Frontend:** http://localhost:5173
- **API:** http://localhost:8080
- **API docs (Swagger):** http://localhost:8080/docs

```bash
# Stop everything
Ctrl+C
docker compose down

# Run in background
docker compose up --build -d
docker compose logs -f         # follow all logs
docker compose logs -f api     # follow API logs only
docker compose logs -f worker  # follow worker logs only
docker compose down            # stop
```

### Option B: Run each service manually

You need 4 terminal windows.

**Terminal 1 -- Firestore emulator:**
```bash
gcloud emulators firestore start --host-port=localhost:8681
```

**Terminal 2 -- Backend API:**
```bash
source venv/bin/activate
export FIRESTORE_EMULATOR_HOST=localhost:8681
export PUBSUB_EMULATOR_HOST=localhost:8085
uvicorn src.api.main:app --reload --port 8080
```

**Terminal 3 -- Worker:**
```bash
source venv/bin/activate
export FIRESTORE_EMULATOR_HOST=localhost:8681
export PUBSUB_EMULATOR_HOST=localhost:8085
python -m src.worker.consumer
```

**Terminal 4 -- Frontend:**
```bash
cd frontend
npm run dev
# Opens at http://localhost:5173
```

---

## Testing the API

Once the API is running at http://localhost:8080:

### Health check

```bash
curl http://localhost:8080/api/health
```

```json
{"status": "healthy", "version": "1.0.0", "timestamp": "2026-04-23T12:00:00+00:00"}
```

### Create a campaign

```bash
curl -X POST http://localhost:8080/api/campaigns \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Q2 Product Launch",
    "quality": {
      "codec": "copy",
      "resolution": "original",
      "audio_bitrate": "original"
    }
  }'
```

```json
{
  "id": "campaign-uuid",
  "name": "Q2 Product Launch",
  "status": "draft",
  "quality": {"codec": "copy", "resolution": "original", "audio_bitrate": "original"},
  "total_combinations": 0,
  "completed_count": 0,
  "failed_count": 0
}
```

### Get a signed upload URL

```bash
curl -X POST http://localhost:8080/api/upload/signed-url \
  -H "Content-Type: application/json" \
  -d '{
    "campaign_id": "campaign-uuid",
    "type": "intro",
    "filename": "hook_energetic.mp4",
    "content_type": "video/mp4"
  }'
```

```json
{
  "upload_url": "https://storage.googleapis.com/...(signed URL)...",
  "video_id": "video-uuid",
  "gcs_path": "uploads/user123/intros/video-uuid.mp4"
}
```

### Upload a file to the signed URL

```bash
curl -X PUT "SIGNED_URL_FROM_ABOVE" \
  -H "Content-Type: video/mp4" \
  --data-binary @/path/to/your/video.mp4
```

### Register the uploaded video

```bash
curl -X POST http://localhost:8080/api/campaigns/campaign-uuid/videos \
  -H "Content-Type: application/json" \
  -d '{"video_id": "video-uuid"}'
```

```json
{
  "id": "video-uuid",
  "type": "intro",
  "filename": "hook_energetic.mp4",
  "duration_seconds": 5.2,
  "codec": "h264",
  "width": 1920,
  "height": 1080
}
```

### Start the campaign (trigger merges)

After uploading intros and mains:

```bash
curl -X POST http://localhost:8080/api/campaigns/campaign-uuid/start
```

```json
{
  "status": "processing",
  "total_combinations": 50
}
```

### Check campaign progress

```bash
curl http://localhost:8080/api/campaigns/campaign-uuid
```

```json
{
  "id": "campaign-uuid",
  "name": "Q2 Product Launch",
  "status": "processing",
  "total_combinations": 50,
  "completed_count": 32,
  "failed_count": 1,
  "created_at": "2026-04-23T12:00:00+00:00"
}
```

### List completed results

```bash
curl "http://localhost:8080/api/campaigns/campaign-uuid/results?status=completed"
```

```json
[
  {
    "id": "combination-uuid",
    "intro_name": "hook_energetic.mp4",
    "main_name": "product_demo.mp4",
    "status": "completed",
    "output_size_bytes": 15728640,
    "duration_seconds": 35.2,
    "download_url": "https://storage.googleapis.com/...(signed URL)..."
  }
]
```

### Download a specific result

```bash
curl http://localhost:8080/api/download/combination-uuid
```

```json
{"download_url": "https://storage.googleapis.com/...(signed URL, 1hr expiry)..."}
```

---

## Frontend Development

```bash
cd frontend

# Start dev server with hot reload
npm run dev
# Opens at http://localhost:5173

# Type checking
npm run typecheck

# Lint
npm run lint

# Build for production
npm run build
# Output in frontend/dist/

# Preview production build locally
npm run preview
```

**Environment variables** (in `frontend/.env.local`):

```
VITE_API_URL=http://localhost:8080/api
```

For production builds, set `VITE_API_URL` to the Cloud Run API URL.

---

## Deploying to GCP

The sandbox environment is already provisioned. These instructions are for deploying code to it.

**Sandbox project:** `sandbox-456317` | **Account:** `sandbox1@zimran.io` | **Region:** `us-central1`

### Step 1: Authenticate

```bash
gcloud auth login sandbox1@zimran.io
gcloud config set project sandbox-456317
gcloud auth configure-docker us-central1-docker.pkg.dev
```

### Step 2: Build and push Docker images

```bash
# Backend image (API + worker)
docker build -t us-central1-docker.pkg.dev/sandbox-456317/vgen/backend:latest .
docker push us-central1-docker.pkg.dev/sandbox-456317/vgen/backend:latest

# Frontend image
docker build -f Dockerfile.frontend \
  --build-arg VITE_API_URL=https://vgen-api-<hash>.us-central1.run.app/api \
  -t us-central1-docker.pkg.dev/sandbox-456317/vgen/frontend:latest .
docker push us-central1-docker.pkg.dev/sandbox-456317/vgen/frontend:latest
```

### Step 3: Deploy with Terraform

```bash
cd infrastructure

# Initialize (first time only)
terraform init

# Preview changes
terraform plan

# Deploy (type 'yes' when prompted)
terraform apply

# Get service URLs
terraform output
```

### Step 4: Verify

```bash
curl $(terraform output -raw api_url)/api/health
```

### Automated deploys (CI/CD)

Once the GitHub repo is connected to Cloud Build, every push to `main` auto-deploys:

1. **One-time setup:** Go to [Cloud Build Triggers](https://console.cloud.google.com/cloud-build/triggers?project=sandbox-456317) > Connect Repository > GitHub
2. After connecting, Terraform creates the trigger automatically
3. Every push to `main` runs `cloudbuild.yaml` which builds both images and deploys all 3 services

To trigger a manual build:
```bash
gcloud builds submit --config=cloudbuild.yaml --project=sandbox-456317
```

### Sandbox resources (already provisioned)

| Resource | Name |
|----------|------|
| GCS uploads bucket | `sandbox-456317-vgen-uploads` |
| GCS outputs bucket | `sandbox-456317-vgen-outputs` |
| Pub/Sub topic | `merge-tasks` |
| Pub/Sub subscription | `merge-tasks-sub` |
| Pub/Sub DLQ | `merge-tasks-dlq` |
| Firestore database | `(default)` native mode |
| Artifact Registry | `us-central1-docker.pkg.dev/sandbox-456317/vgen` |
| Terraform state | `gs://sandbox-456317-tf-state/vgen` |

---

## Common Issues

| Problem | Cause | Fix |
|---------|-------|-----|
| `FIRESTORE_EMULATOR_HOST not set` | Emulator not running or env var missing | Start emulator: `gcloud emulators firestore start --host-port=localhost:8681` and export the var |
| `403 Forbidden` on GCS upload | Missing permissions | Run `gcloud auth application-default login` or check service account IAM roles |
| `FFmpeg not found` | Not installed on host | Docker includes it. For local dev: `brew install ffmpeg` (macOS) or `apt install ffmpeg` (Linux) |
| CORS errors in frontend | API not allowing frontend origin | Check CORS middleware config in `src/api/main.py`. Local dev should allow `localhost:5173` |
| `Connection refused` on port 8080 | API not running | Start API first: `uvicorn src.api.main:app --port 8080` or `docker compose up` |
| Signed URL upload returns 403 | URL expired or wrong content-type | URLs expire after 60min. Ensure `Content-Type` header matches what was requested |
| Worker not processing messages | Pub/Sub subscription misconfigured | Check `PUBSUB_EMULATOR_HOST` is set. Verify subscription exists: `gcloud pubsub subscriptions list` |
| `terraform init` fails | Backend bucket doesn't exist | Create GCS bucket for Terraform state first, or use local backend for dev |

---

## Commands Cheat Sheet

```bash
# ============ SETUP ============
python3 -m venv venv && source venv/bin/activate   # Python venv
pip install -r requirements.txt                     # Backend deps
cd frontend && npm install && cd ..                 # Frontend deps

# ============ RUN (Docker -- start everything) ============
docker compose up --build          # start all services
docker compose down                # stop all services
docker compose logs -f api         # follow API logs
docker compose logs -f worker      # follow worker logs

# ============ RUN (manual -- 4 terminals) ============
gcloud emulators firestore start --host-port=localhost:8681   # T1: emulator
uvicorn src.api.main:app --reload --port 8080                 # T2: API
python -m src.worker.consumer                                 # T3: worker
cd frontend && npm run dev                                    # T4: frontend

# ============ TEST ============
curl http://localhost:8080/api/health                         # health check
pytest tests/                                                 # run tests
cd frontend && npm run typecheck                              # TS check

# ============ BUILD ============
docker build -t vgen-backend .                                # backend image
docker build -f Dockerfile.frontend -t vgen-frontend .        # frontend image
cd frontend && npm run build                                  # frontend static

# ============ DEPLOY ============
cd infrastructure
terraform init                     # first time only
terraform plan                     # preview changes
terraform apply                    # deploy to GCP
terraform output                   # show URLs
```
