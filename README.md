# HealOps AI

HealOps AI is a full-stack Kubernetes observability and safe AI-assisted recovery platform.

## Current implementation

- React 19 + TypeScript + Vite light-theme frontend with all requested navigation pages
- FastAPI backend with Kubernetes and Prometheus integrations
- SQLite persistence for incidents and recovery history
- Isolation Forest model with baseline collection and configurable contamination
- Deployment-pod restart recovery with ownership validation
- Explicit unavailable states when kubeconfig or Prometheus is missing

## Run locally

### Frontend

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

Open http://127.0.0.1:5173.

### Backend

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

API documentation is at http://127.0.0.1:8000/docs.

Set `PROMETHEUS_URL`, `KUBECONFIG`, `AI_CONTAMINATION`, `AI_MIN_BASELINE_SAMPLES`, and recovery environment variables in a process environment or `.env`-compatible startup configuration.

## Kubernetes requirements

Install kubectl and configure the local kubeconfig. The backend automatically loads the current kubeconfig or in-cluster configuration. No cluster is modified at startup.

Safe recovery:

- Only pods owned by a ReplicaSet owned by a Deployment are eligible
- The pod is deleted so Kubernetes recreates it
- API acceptance is stored separately from workload verification
- Automated recovery remains disabled by default

## Infrastructure scripts

The application does not recreate or delete an existing cluster. Install Prometheus and Grafana separately, or use your existing services.
