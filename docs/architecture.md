# Architecture

The frontend is a React/Vite application. FastAPI exposes cluster, node, pod, metric, AI, incident, recovery, analytics, and settings APIs.

Prometheus supplies historical metrics. Kubernetes supplies authoritative node, pod, workload, event, and log state. SQLite persists incidents and recovery records.

Isolation Forest receives normalized CPU, memory, and restart features after baseline collection. An anomaly creates an incident and recommendation. Recovery is restricted to deleting a pod owned by a Deployment-managed ReplicaSet.

The Kubernetes API request does not imply success. The verification endpoint queries replacement pod health and only resolves the incident when the replacement is Running and all containers are Ready.
