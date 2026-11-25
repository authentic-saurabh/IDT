import os
import sqlite3
import time
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    from kubernetes import client, config
    KUBE_AVAILABLE = True
except Exception:
    client = None
    config = None
    KUBE_AVAILABLE = False

try:
    import numpy as np
    from sklearn.ensemble import IsolationForest
    import joblib
    AI_AVAILABLE = True
except Exception:
    np = None
    IsolationForest = None
    joblib = None
    AI_AVAILABLE = False

DB_PATH = os.getenv("HEALOPS_DB", os.path.join(os.path.dirname(__file__), "healops.db"))
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090").rstrip("/")

@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_monitoring_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="HealOps AI API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS incidents (
            id TEXT PRIMARY KEY, timestamp TEXT, severity TEXT, resource_type TEXT,
            resource_name TEXT, namespace TEXT, metric TEXT, score REAL,
            description TEXT, status TEXT
        );
        CREATE TABLE IF NOT EXISTS recoveries (
            id TEXT PRIMARY KEY, incident_id TEXT, workload TEXT, action TEXT,
            start_time TEXT, completion_time TEXT, duration_seconds REAL,
            verification TEXT, status TEXT, namespace TEXT
        );
        CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, actor TEXT,
            action TEXT, details TEXT
        );
    """)
    try:
        conn.execute("ALTER TABLE recoveries ADD COLUMN namespace TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


init_db()

model = None
model_training_time = None
model_samples = 0
baseline_samples: list[list[float]] = []
MODEL_PATH = os.path.join(os.path.dirname(__file__), "isolation_forest.joblib")


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def _parse_kubernetes_quantity(value: str) -> int:
    if not isinstance(value, str):
        return 0
    value = value.strip()
    if value.endswith("Ki"):
        return int(float(value[:-2]) * 1024)
    if value.endswith("Mi"):
        return int(float(value[:-2]) * 1024**2)
    if value.endswith("Gi"):
        return int(float(value[:-2]) * 1024**3)
    if value.endswith("Ti"):
        return int(float(value[:-2]) * 1024**4)
    try:
        return int(float(value))
    except ValueError:
        return 0


def _parse_cpu_millicores(value: str) -> int:
    if not isinstance(value, str):
        return 0
    value = value.strip()
    if value.endswith("m"):
        try:
            return int(float(value[:-1]))
        except ValueError:
            return 0
    try:
        return int(float(value) * 1000)
    except ValueError:
        return 0


if AI_AVAILABLE and os.path.exists(MODEL_PATH):
    try:
        model = joblib.load(MODEL_PATH)
        model_training_time = utcnow()
    except Exception:
        model = None


def kube_api():
    if not KUBE_AVAILABLE:
        raise HTTPException(503, "Kubernetes Python client is unavailable")
    kubeconfig = os.getenv("KUBECONFIG")
    try:
        if kubeconfig:
            config.load_kube_config(config_file=kubeconfig)
        else:
            config.load_kube_config()
    except Exception:
        try:
            config.load_incluster_config()
        except Exception as exc:
            raise HTTPException(503, f"No Kubernetes configuration available: {exc}") from exc
    return client.CoreV1Api(), client.AppsV1Api()


def prometheus_query(query: str):
    try:
        with httpx.Client(timeout=4.0) as http:
            response = http.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query})
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") != "success":
                return None, payload.get("error", "Prometheus query failed")
            return payload["data"]["result"], None
    except Exception as exc:
        return None, str(exc)


@app.get("/api/health")
def health():
    prometheus_result, prometheus_error = prometheus_query("up")
    cluster_status = "disconnected"
    try:
        kube_api()
        cluster_status = "connected"
    except HTTPException:
        pass
    return {
        "status": "running",
        "cluster": cluster_status,
        "prometheus": "available" if prometheus_error is None and bool(prometheus_result) else "unavailable",
        "ai": "available" if AI_AVAILABLE else "unavailable",
        "timestamp": utcnow(),
    }


@app.get("/api/cluster")
def cluster():
    try:
        core, apps = kube_api()
        nodes = core.list_node().items
        pods = core.list_pod_for_all_namespaces().items
        cpu_capacity = sum(_parse_cpu_millicores(node.status.allocatable.get("cpu", "0")) for node in nodes)
        return {
            "name": "kind-cluster",
            "status": "connected",
            "kubernetesVersion": getattr(nodes[0].status.node_info, "kubelet_version", "Unknown") if nodes else "Unknown",
            "nodeCount": len(nodes),
            "podCount": len(pods),
            "healthyPods": sum(p.status.phase == "Running" for p in pods),
            "unhealthyPods": sum(p.status.phase not in ("Running", "Succeeded") for p in pods),
            "cpuCapacityMillicores": cpu_capacity,
            "memoryCapacityBytes": sum(_parse_kubernetes_quantity(node.status.capacity.get("memory", "0")) for node in nodes),
        }
    except HTTPException as exc:
        return {"name": "Unavailable", "status": "disconnected", "kubernetesVersion": "Unavailable", "nodeCount": 0, "podCount": 0, "healthyPods": 0, "unhealthyPods": 0, "error": exc.detail}


@app.get("/api/nodes")
def nodes():
    try:
        core, _ = kube_api()
        result = []
        cpu_series, _ = prometheus_query(
            "100 * (1 - avg by(instance) (rate(node_cpu_seconds_total{mode=\"idle\"}[5m])))"
        )
        memory_series, _ = prometheus_query(
            "100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))"
        )
        cpu_by_instance = {
            str(row["metric"].get("instance", "")).split(":")[0]: float(row["value"][1])
            for row in (cpu_series or [])
            if row.get("value")
        }
        memory_by_instance = {
            str(row["metric"].get("instance", "")).split(":")[0]: float(row["value"][1])
            for row in (memory_series or [])
            if row.get("value")
        }
        for node in core.list_node().items:
            conditions = {c.type: c.status for c in (node.status.conditions or [])}
            role = "Control Plane" if any(k.startswith("node-role.kubernetes.io/control-plane") for k in (node.metadata.labels or {})) else "Worker"
            internal_ip = next((a.address for a in (node.status.addresses or []) if a.type == "InternalIP"), "Unavailable")
            result.append({
                "name": node.metadata.name,
                "role": role,
                "status": "Ready" if conditions.get("Ready") == "True" else "Not Ready",
                "cpuCapacity": node.status.capacity.get("cpu", "Unknown"),
                "memoryCapacity": node.status.capacity.get("memory", "Unknown"),
                "cpuUsage": round(cpu_by_instance.get(internal_ip, 0.0), 1) if internal_ip in cpu_by_instance else None,
                "memoryUsage": round(memory_by_instance.get(internal_ip, 0.0), 1) if internal_ip in memory_by_instance else None,
                "podCount": sum(1 for p in core.list_pod_for_all_namespaces().items if p.spec.node_name == node.metadata.name),
                "kubernetesVersion": node.status.node_info.kubelet_version,
                "internalIp": internal_ip,
            })
        return result
    except HTTPException as exc:
        raise exc


@app.get("/api/nodes/{name}")
def node_detail(name: str):
    try:
        core, _ = kube_api()
        node = core.read_node(name)
        pods = [
            pod.metadata.name
            for pod in core.list_pod_for_all_namespaces().items
            if pod.spec.node_name == name
        ]
        events = [
            {
                "timestamp": event.last_timestamp.isoformat() if event.last_timestamp else None,
                "reason": event.reason,
                "message": event.message,
                "type": event.type,
            }
            for event in core.list_event_for_all_namespaces(
                field_selector=f"involvedObject.name={name}"
            ).items
        ]
        return {
            "name": node.metadata.name,
            "conditions": [
                {
                    "type": condition.type,
                    "status": condition.status,
                    "reason": condition.reason,
                    "message": condition.message,
                }
                for condition in (node.status.conditions or [])
            ],
            "allocatable": node.status.allocatable or {},
            "capacity": node.status.capacity or {},
            "pods": pods,
            "events": events,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/pods")
def pods(namespace: str | None = None):
    try:
        core, _ = kube_api()
        items = core.list_namespaced_pod(namespace).items if namespace else core.list_pod_for_all_namespaces().items
        cpu_series, _ = prometheus_query(
            "sum by(namespace,pod) (rate(container_cpu_usage_seconds_total[5m]))"
        )
        memory_series, _ = prometheus_query(
            "sum by(namespace,pod) (container_memory_working_set_bytes)"
        )
        cpu_by_pod = {
            f"{row['metric'].get('namespace','')}/{row['metric'].get('pod','')}": float(row["value"][1])
            for row in (cpu_series or []) if row.get("value")
        }
        memory_by_pod = {
            f"{row['metric'].get('namespace','')}/{row['metric'].get('pod','')}": float(row["value"][1])
            for row in (memory_series or []) if row.get("value")
        }
        return [{
            "name": p.metadata.name,
            "namespace": p.metadata.namespace,
            "node": p.spec.node_name or "Pending",
            "status": p.status.phase,
            "cpuUsage": round(cpu_by_pod.get(f"{p.metadata.namespace}/{p.metadata.name}", 0.0), 4)
            if f"{p.metadata.namespace}/{p.metadata.name}" in cpu_by_pod else None,
            "memoryUsage": memory_by_pod.get(f"{p.metadata.namespace}/{p.metadata.name}"),
            "restartCount": sum(c.restart_count for c in (p.status.container_statuses or [])),
            "created": p.metadata.creation_timestamp.isoformat() if p.metadata.creation_timestamp else None,
            "readyContainers": sum(1 for c in (p.status.container_statuses or []) if c.ready),
            "totalContainers": len(p.spec.containers),
        } for p in items]
    except HTTPException as exc:
        raise exc


@app.get("/api/namespaces")
def namespaces():
    try:
        core, _ = kube_api()
        return [
            {
                "name": namespace.metadata.name,
                "status": namespace.status.phase,
                "labels": namespace.metadata.labels or {},
            }
            for namespace in core.list_namespace().items
        ]
    except HTTPException:
        raise


@app.get("/api/workloads")
def workloads(namespace: str | None = None):
    try:
        _, apps = kube_api()
        core, _ = kube_api()
        deployment_items = apps.list_namespaced_deployment(namespace).items if namespace else apps.list_deployment_for_all_namespaces().items
        stateful_items = apps.list_namespaced_stateful_set(namespace).items if namespace else apps.list_stateful_set_for_all_namespaces().items
        daemon_items = apps.list_namespaced_daemon_set(namespace).items if namespace else apps.list_daemon_set_for_all_namespaces().items
        return {
            "deployments": [
                {
                    "name": item.metadata.name,
                    "namespace": item.metadata.namespace,
                    "kind": "Deployment",
                    "replicas": item.status.ready_replicas or 0,
                    "desired": item.spec.replicas or 0,
                    "created": item.metadata.creation_timestamp.isoformat() if item.metadata.creation_timestamp else None,
                }
                for item in deployment_items
            ],
            "statefulSets": [
                {
                    "name": item.metadata.name,
                    "namespace": item.metadata.namespace,
                    "kind": "StatefulSet",
                    "replicas": item.status.ready_replicas or 0,
                    "desired": item.spec.replicas or 0,
                    "created": item.metadata.creation_timestamp.isoformat() if item.metadata.creation_timestamp else None,
                }
                for item in stateful_items
            ],
            "daemonSets": [
                {
                    "name": item.metadata.name,
                    "namespace": item.metadata.namespace,
                    "kind": "DaemonSet",
                    "replicas": item.status.number_ready or 0,
                    "desired": item.status.desired_number_scheduled or 0,
                    "created": item.metadata.creation_timestamp.isoformat() if item.metadata.creation_timestamp else None,
                }
                for item in daemon_items
            ],
        }
    except HTTPException:
        raise


@app.get("/api/pods/{namespace}/{name}")
def pod_detail(namespace: str, name: str):
    try:
        core, _ = kube_api()
        pod = core.read_namespaced_pod(name, namespace)
        events = core.list_namespaced_event(
            namespace,
            field_selector=f"involvedObject.name={name}",
        ).items
        logs = {}
        for container in pod.spec.containers:
            try:
                logs[container.name] = core.read_namespaced_pod_log(name, namespace, container=container.name, tail_lines=100)
            except Exception as exc:
                logs[container.name] = f"Logs unavailable: {exc}"
        return {
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "status": pod.status.phase,
            "node": pod.spec.node_name,
            "labels": pod.metadata.labels or {},
            "containers": [
                {
                    "name": c.name,
                    "image": c.image,
                    "ready": next((s.ready for s in (pod.status.container_statuses or []) if s.name == c.name), False),
                    "restartCount": next((s.restart_count for s in (pod.status.container_statuses or []) if s.name == c.name), 0),
                }
                for c in pod.spec.containers
            ],
            "conditions": [
                {"type": c.type, "status": c.status, "reason": c.reason, "message": c.message}
                for c in (pod.status.conditions or [])
            ],
            "events": [
                {
                    "timestamp": e.last_timestamp.isoformat() if e.last_timestamp else (e.event_time.isoformat() if e.event_time else None),
                    "reason": e.reason,
                    "message": e.message,
                    "type": e.type,
                }
                for e in events
            ],
            "logs": logs,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/metrics/{kind}")
def metric(kind: str, metric: str | None = None, range: str = "30m", step: str = "30s"):
    if kind == "range":
        return metrics_range(metric or "cpu", range, step)
    queries = {
        "cpu": "sum(rate(container_cpu_usage_seconds_total[5m]))",
        "memory": "sum(container_memory_working_set_bytes)",
        "pods": "sum(kube_pod_status_phase{phase=\"Running\"})",
    }
    if kind not in queries:
        raise HTTPException(404, "Unknown metric")
    result, error = prometheus_query(queries[kind])
    if error:
        return {"kind": kind, "available": False, "message": "Prometheus unavailable or metric series missing", "detail": error, "series": []}
    return {"kind": kind, "available": True, "series": [{"timestamp": r["value"][0], "value": float(r["value"][1])} for r in result]}


@app.get("/api/metrics/overview")
def metrics_overview():
    cpu, cpu_error = prometheus_query("sum(rate(container_cpu_usage_seconds_total[5m]))")
    memory, memory_error = prometheus_query("sum(container_memory_working_set_bytes)")
    return {
        "cpu": None if cpu_error else (float(cpu[0]["value"][1]) if cpu else None),
        "memory": None if memory_error else (float(memory[0]["value"][1]) if memory else None),
        "available": not cpu_error and not memory_error,
        "timestamp": utcnow(),
    }


@app.get("/api/metrics/range")
def metrics_range(metric: str = "cpu", range: str = "30m", step: str = "30s"):
    queries = {
        "cpu": "sum(rate(container_cpu_usage_seconds_total[5m]))",
        "memory": "sum(container_memory_working_set_bytes)",
        "running_pods": "sum(kube_pod_status_phase{phase=\"Running\"})",
        "restarts": "sum(increase(kube_pod_container_status_restarts_total[5m]))",
    }
    if metric not in queries:
        raise HTTPException(404, "Unknown metric")
    try:
        range_seconds = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "6h": 21600, "24h": 86400}.get(range, 1800)
        end = time.time()
        start = end - range_seconds
        with httpx.Client(timeout=5.0) as http:
            response = http.get(
                f"{PROMETHEUS_URL}/api/v1/query_range",
                params={"query": queries[metric], "start": start, "end": end, "step": step},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        return {"metric": metric, "available": False, "message": "Prometheus unavailable or metric series missing", "detail": str(exc), "values": []}
    if payload.get("status") != "success":
        return {"metric": metric, "available": False, "message": payload.get("error", "Prometheus query failed"), "values": []}
    values = []
    for series in payload["data"]["result"]:
        labels = series.get("metric", {})
        for timestamp, value in series.get("values", []):
            try:
                values.append({"timestamp": timestamp, "value": float(value), "labels": labels})
            except (TypeError, ValueError):
                continue
    return {"metric": metric, "available": bool(values), "values": values}


@app.get("/api/ai/status")
def ai_status():
    conn = db()
    anomaly_count = conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
    conn.close()
    return {
        "status": "running" if AI_AVAILABLE else "stopped",
        "modelName": "HealOps Isolation Forest",
        "algorithm": "Isolation Forest",
        "trained": model is not None,
        "lastAnalysis": model_training_time,
        "samples": model_samples,
        "baselineNeeded": int(os.getenv("AI_MIN_BASELINE_SAMPLES", "30")),
        "anomalyCount": anomaly_count,
        "contamination": float(os.getenv("AI_CONTAMINATION", "0.05")),
    }


class AnalysisRequest(BaseModel):
    cpu: float
    memory: float
    restarts: float = 0


@app.post("/api/ai/analyse")
def analyse(payload: AnalysisRequest):
    global model, model_training_time, model_samples
    sample = [payload.cpu, payload.memory, payload.restarts]
    baseline_samples.append(sample)
    if len(baseline_samples) > 500:
        baseline_samples.pop(0)
    min_samples = int(os.getenv("AI_MIN_BASELINE_SAMPLES", "30"))
    if len(baseline_samples) >= min_samples and AI_AVAILABLE:
        model = IsolationForest(contamination=float(os.getenv("AI_CONTAMINATION", "0.05")), random_state=42)
        model.fit(np.asarray(baseline_samples, dtype=float))
        if joblib is not None:
            joblib.dump(model, MODEL_PATH)
        model_training_time = utcnow()
        model_samples = len(baseline_samples)
    if model is None:
        return {"trained": False, "anomaly": False, "score": 0.0, "message": f"Collecting baseline: {len(baseline_samples)}/{min_samples}"}
    prediction = int(model.predict(np.asarray([sample], dtype=float))[0])
    raw_score = float(-model.score_samples(np.asarray([sample], dtype=float))[0])
    anomaly = prediction == -1
    severity = "Critical" if raw_score > 0.75 else "Warning" if anomaly else "Normal"
    confidence = round(max(0.0, min(1.0, (raw_score + 0.5) / 1.5)) * 100, 1)
    if anomaly:
        incident_id = f"INC-{int(time.time())}"
        conn = db()
        conn.execute("""INSERT OR REPLACE INTO incidents
            (id,timestamp,severity,resource_type,resource_name,namespace,metric,score,description,status)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                incident_id,
                utcnow(),
                severity,
                "Workload",
                "Prometheus observation",
                "unknown",
                "CPU/Memory/Restart composite",
                raw_score,
                "Isolation Forest classified this observation as anomalous.",
                "Detected",
            ),
        )
        conn.commit()
        conn.close()
    return {
        "trained": True,
        "anomaly": anomaly,
        "score": raw_score,
        "confidence": confidence,
        "severity": severity,
        "affectedMetric": "CPU/Memory/Restart composite",
        "message": "Anomalous resource behaviour detected" if anomaly else "Observation within learned baseline",
    }


@app.get("/api/incidents")
def incidents():
    conn = db()
    rows = conn.execute("SELECT * FROM incidents ORDER BY timestamp DESC").fetchall()
    conn.close()
    result = []
    for row in rows:
        item = dict(row)
        item["confidence"] = round(max(0.0, min(100.0, float(item.get("score") or 0) * 100)), 1)
        result.append(item)
    return result


@app.get("/api/incidents/{incident_id}")
def incident_detail(incident_id: str):
    conn = db()
    incident = conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
    recoveries = conn.execute("SELECT * FROM recoveries WHERE incident_id = ? ORDER BY start_time", (incident_id,)).fetchall()
    conn.close()
    if incident is None:
        raise HTTPException(404, "Incident not found")
    item = dict(incident)
    item["confidence"] = round(max(0.0, min(100.0, float(item.get("score") or 0) * 100)), 1)
    item["timeline"] = [
        {"step": "Initial metric observation", "timestamp": item["timestamp"], "status": "Recorded"},
        {"step": "AI anomaly detection", "timestamp": item["timestamp"], "status": item["severity"]},
        {"step": "Affected resource identification", "timestamp": item["timestamp"], "status": item["resource_name"]},
        {"step": "Recovery recommendation", "timestamp": item["timestamp"], "status": "Pod restart only if Deployment-managed"},
        *[
            {"step": "Recovery attempt", "timestamp": r["start_time"], "status": r["status"], "details": r["action"]}
            for r in recoveries
        ],
    ]
    return item


@app.post("/api/incidents")
def create_incident(payload: dict):
    incident_id = payload.get("id") or f"INC-{int(time.time())}"
    conn = db()
    conn.execute("""INSERT OR REPLACE INTO incidents
        (id,timestamp,severity,resource_type,resource_name,namespace,metric,score,description,status)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (incident_id, payload.get("timestamp", utcnow()), payload.get("severity", "Warning"),
         payload.get("resource_type", "Pod"), payload.get("resource_name", "Unknown"),
         payload.get("namespace", "default"), payload.get("metric", "Composite"),
         payload.get("score", 0), payload.get("description", ""), payload.get("status", "Detected")))
    conn.commit()
    conn.close()
    return {"id": incident_id, "status": "created"}


@app.get("/api/recovery/history")
def recovery_history():
    conn = db()
    rows = conn.execute("SELECT * FROM recoveries ORDER BY start_time DESC").fetchall()
    conn.close()
    result = []
    for row in rows:
        item = dict(row)
        conn = db()
        incident = conn.execute(
            "SELECT score,severity FROM incidents WHERE id = ?",
            (item.get("incident_id"),),
        ).fetchone()
        conn.close()
        anomaly_confidence = float(incident["score"]) if incident and incident["score"] is not None else 0.5
        anomaly_confidence = max(0.0, min(1.0, anomaly_confidence))
        result.append({
            **item,
            "confidence": round(anomaly_confidence * 100, 1),
            "estimatedSuccess": round(max(45.0, min(99.0, 55.0 + anomaly_confidence * 35.0)), 1),
        })
    return result


class RecoveryRequest(BaseModel):
    incidentId: str | None = None
    namespace: str = "default"
    podName: str


@app.post("/api/recovery/execute")
def execute_recovery(payload: RecoveryRequest):
    started = utcnow()
    recovery_id = f"REC-{int(time.time())}"
    try:
        allowed_namespaces = [
            item.strip()
            for item in os.getenv("HEALOPS_ALLOWED_NAMESPACES", "").split(",")
            if item.strip()
        ]
        if allowed_namespaces and payload.namespace not in allowed_namespaces:
            raise HTTPException(403, "Namespace is not allowlisted for recovery")
        cooldown_seconds = int(os.getenv("RECOVERY_COOLDOWN_SECONDS", "300"))
        conn = db()
        cutoff = datetime.now(timezone.utc).timestamp() - cooldown_seconds
        recent_rows = conn.execute(
            "SELECT start_time FROM recoveries WHERE workload = ? AND namespace = ?",
            (payload.podName, payload.namespace),
        ).fetchall()
        conn.close()
        recent_attempts = sum(
            datetime.fromisoformat(row["start_time"]).timestamp() >= cutoff
            for row in recent_rows
            if row["start_time"]
        )
        if recent_attempts >= 3:
            raise HTTPException(429, "Recovery retry limit reached")
        if recent_attempts:
            raise HTTPException(429, "Recovery cooldown is active")
        core, apps = kube_api()
        pod = core.read_namespaced_pod(payload.podName, payload.namespace)
        owner_refs = pod.metadata.owner_references or []
        replica_name = next((o.name for o in owner_refs if o.kind == "ReplicaSet"), None)
        if not replica_name:
            raise HTTPException(400, "Pod is not managed by a Restartable ReplicaSet")
        replica_set = apps.read_namespaced_replica_set(replica_name, payload.namespace)
        deployment_owner = next((o.name for o in (replica_set.metadata.owner_references or []) if o.kind == "Deployment"), None)
        if not deployment_owner:
            raise HTTPException(400, "Pod is not owned by a supported Deployment")
        deployment = apps.read_namespaced_deployment(deployment_owner, payload.namespace)
        if (deployment.spec.replicas or 1) < 1:
            raise HTTPException(400, "Deployment has no configured replicas")
        core.delete_namespaced_pod(payload.podName, payload.namespace)
        completed = utcnow()
        status = "Verification Pending"
        verification = "Pod deletion accepted; workload health verification is required"
    except HTTPException as exc:
        completed = utcnow()
        status = "Failed"
        verification = exc.detail
    except Exception as exc:
        completed = utcnow()
        status = "Failed"
        verification = str(exc)
    duration = max(0.0, datetime.now(timezone.utc).timestamp() - datetime.fromisoformat(started).timestamp())
    conn = db()
    conn.execute("""INSERT INTO recoveries
        (id,incident_id,workload,action,start_time,completion_time,duration_seconds,verification,status,namespace)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (recovery_id, payload.incidentId, payload.podName, "Restart pod",
         started, completed, duration, verification, status, payload.namespace))
    conn.commit()
    conn.close()
    return {"id": recovery_id, "status": status, "verification": verification}


@app.post("/api/recovery/{recovery_id}/verify")
def verify_recovery(recovery_id: str):
    conn = db()
    recovery = conn.execute("SELECT * FROM recoveries WHERE id = ?", (recovery_id,)).fetchone()
    if recovery is None:
        conn.close()
        raise HTTPException(404, "Recovery not found")
    workload = recovery["workload"]
    namespace = recovery["namespace"] or "default"
    conn.close()
    try:
        core, _ = kube_api()
        replacement = None
        prefix = "-".join(workload.split("-")[:-1])
        candidates = core.list_namespaced_pod(namespace).items
        for candidate in candidates:
            if candidate.metadata.deletion_timestamp is None and (
                candidate.metadata.name.startswith(prefix + "-") or candidate.metadata.name == workload
            ):
                replacement = candidate
                break
        ready = bool(replacement and replacement.status.phase == "Running" and replacement.status.container_statuses and all(
            container.ready for container in (replacement.status.container_statuses or [])
        ))
        if ready:
            status = "Resolved"
            verification = "Replacement pod is Running and all containers are ready"
        else:
            status = "Verification Failed"
            replacement_phase = replacement.status.phase if replacement else "not found"
            verification = f"Replacement pod state is {replacement_phase}; containers are not all ready"
    except HTTPException as exc:
        status = "Verification Failed"
        verification = exc.detail
    except Exception as exc:
        status = "Verification Failed"
        verification = str(exc)
    conn = db()
    conn.execute(
        "UPDATE recoveries SET status = ?, verification = ?, completion_time = ? WHERE id = ?",
        (status, verification, utcnow(), recovery_id),
    )
    if status == "Resolved" and recovery["incident_id"]:
        conn.execute(
            "UPDATE incidents SET status = 'Resolved' WHERE id = ?",
            (recovery["incident_id"],),
        )
    conn.commit()
    conn.close()
    return {"id": recovery_id, "status": status, "verification": verification}


@app.get("/api/analytics/summary")
def analytics_summary():
    conn = db()
    incident_count = conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
    incident_rows = conn.execute("SELECT score FROM incidents").fetchall()
    recs = conn.execute("SELECT status,duration_seconds FROM recoveries").fetchall()
    conn.close()
    successful = sum(r["status"] == "Resolved" for r in recs)
    failed = sum(r["status"] == "Failed" for r in recs)
    durations = [r["duration_seconds"] for r in recs if r["duration_seconds"] is not None]
    success_rate = round(successful / len(recs) * 100, 1) if recs else 0
    mean_recovery = round(sum(durations) / len(durations), 1) if durations else 0
    incident_scores = [max(0.0, min(1.0, float(r["score"] or 0))) for r in incident_rows]
    average_confidence = round(sum(incident_scores) / len(incident_scores) * 100, 1) if incident_scores else 0
    estimated_success = round(max(45.0, min(99.0, (success_rate or 55.0) * 0.65 + average_confidence * 0.35)), 1)

    estimated_manual_detection_seconds = 900
    estimated_manual_recovery_seconds = 1200
    without_mttr = estimated_manual_detection_seconds + estimated_manual_recovery_seconds
    with_mttr = mean_recovery
    downtime_reduction = round((1 - (with_mttr / without_mttr)) * 100, 1) if with_mttr else 0
    return {
        "incidentCount": incident_count,
        "recoveryAttempts": len(recs),
        "successfulRecoveries": successful,
        "failedRecoveries": failed,
        "successRate": success_rate,
        "meanTimeToRecovery": mean_recovery,
        "averageConfidence": average_confidence,
        "estimatedRecoverySuccess": estimated_success,
        "performanceComparison": {
            "withHealOps": {
                "meanDetectionSeconds": with_mttr,
                "meanRecoverySeconds": with_mttr,
                "totalResponseSeconds": with_mttr,
                "source": "Measured from persisted recovery records",
            },
            "withoutHealOps": {
                "meanDetectionSeconds": estimated_manual_detection_seconds,
                "meanRecoverySeconds": estimated_manual_recovery_seconds,
                "totalResponseSeconds": without_mttr,
                "source": "College-deployment baseline estimate",
            },
            "responseImprovementPercent": max(0.0, downtime_reduction),
        },
    }


@app.get("/api/analytics/greenops")
def greenops_summary():
    cpu_requested, cpu_requested_error = prometheus_query(
        "sum(kube_pod_container_resource_requests{resource=\"cpu\"})"
    )
    memory_requested, memory_requested_error = prometheus_query(
        "sum(kube_pod_container_resource_requests{resource=\"memory\"})"
    )
    cpu_used, cpu_used_error = prometheus_query(
        "sum(rate(container_cpu_usage_seconds_total[5m]))"
    )
    memory_used, memory_used_error = prometheus_query(
        "sum(container_memory_working_set_bytes)"
    )

    cpu_allocated = (
        float(cpu_requested[0]["value"][1])
        if not cpu_requested_error and cpu_requested
        else None
    )
    memory_allocated = (
        float(memory_requested[0]["value"][1])
        if not memory_requested_error and memory_requested
        else None
    )
    cpu_usage = (
        float(cpu_used[0]["value"][1])
        if not cpu_used_error and cpu_used
        else None
    )
    memory_usage = (
        float(memory_used[0]["value"][1])
        if not memory_used_error and memory_used
        else None
    )

    available = all(
        value is not None
        for value in (cpu_allocated, memory_allocated, cpu_usage, memory_usage)
    )
    wasted_cpu = max(0.0, cpu_allocated - cpu_usage) if available else None
    wasted_memory_bytes = max(0.0, memory_allocated - memory_usage) if available else None
    wasted_memory_gb = wasted_memory_bytes / (1024 ** 3) if wasted_memory_bytes is not None else None

    watts_per_cpu_core = float(os.getenv("GREENOPS_WATTS_PER_CPU_CORE", "12"))
    watts_per_memory_gb = float(os.getenv("GREENOPS_WATTS_PER_MEMORY_GB", "0.5"))
    daily_kwh = None
    monthly_kwh = None
    estimated_monthly_co2_kg = None
    if wasted_cpu is not None and wasted_memory_gb is not None:
        estimated_watts = (wasted_cpu * watts_per_cpu_core) + (wasted_memory_gb * watts_per_memory_gb)
        daily_kwh = round(estimated_watts * 24 / 1000, 3)
        monthly_kwh = round(daily_kwh * 30, 2)
        estimated_monthly_co2_kg = round(monthly_kwh * 0.42, 2)

    return {
        "available": available,
        "cpuAllocatedCores": round(cpu_allocated, 3) if cpu_allocated is not None else None,
        "cpuUsedCores": round(cpu_usage, 3) if cpu_usage is not None else None,
        "wastedCpuCores": round(wasted_cpu, 3) if wasted_cpu is not None else None,
        "memoryAllocatedGb": round(memory_allocated / (1024 ** 3), 2) if memory_allocated is not None else None,
        "memoryUsedGb": round(memory_usage / (1024 ** 3), 2) if memory_usage is not None else None,
        "wastedMemoryGb": round(wasted_memory_gb, 2) if wasted_memory_gb is not None else None,
        "estimatedDailyEnergySavingsKwh": daily_kwh,
        "estimatedMonthlyEnergySavingsKwh": monthly_kwh,
        "estimatedMonthlyCo2SavingsKg": estimated_monthly_co2_kg,
        "method": "Estimated as allocated resources minus measured 5-minute usage; energy uses configurable watts per CPU core and memory GB.",
        "timestamp": utcnow(),
    }


@app.get("/api/settings")
def settings():
    return {
        "prometheusUrl": PROMETHEUS_URL,
        "pollInterval": int(os.getenv("POLL_INTERVAL_SECONDS", "30")),
        "contamination": float(os.getenv("AI_CONTAMINATION", "0.05")),
        "minBaseline": int(os.getenv("AI_MIN_BASELINE_SAMPLES", "30")),
        "automatedRecovery": os.getenv("AUTOMATED_RECOVERY", "false").lower() == "true",
        "cooldown": int(os.getenv("RECOVERY_COOLDOWN_SECONDS", "300")),
    }


class SettingsUpdate(BaseModel):
    prometheusUrl: str | None = None
    pollInterval: int | None = None
    contamination: float | None = None
    minBaseline: int | None = None
    automatedRecovery: bool | None = None
    cooldown: int | None = None


@app.put("/api/settings")
def update_settings(payload: SettingsUpdate):
    global PROMETHEUS_URL
    if payload.prometheusUrl:
        PROMETHEUS_URL = payload.prometheusUrl.rstrip("/")
        os.environ["PROMETHEUS_URL"] = PROMETHEUS_URL
    if payload.pollInterval is not None:
        os.environ["POLL_INTERVAL_SECONDS"] = str(payload.pollInterval)
    if payload.contamination is not None:
        os.environ["AI_CONTAMINATION"] = str(payload.contamination)
    if payload.minBaseline is not None:
        os.environ["AI_MIN_BASELINE_SAMPLES"] = str(payload.minBaseline)
    if payload.automatedRecovery is not None:
        os.environ["AUTOMATED_RECOVERY"] = str(payload.automatedRecovery).lower()
    if payload.cooldown is not None:
        os.environ["RECOVERY_COOLDOWN_SECONDS"] = str(payload.cooldown)
    conn = db()
    conn.execute(
        "INSERT INTO audit (timestamp,actor,action,details) VALUES (?,?,?,?)",
        (utcnow(), "operator", "Update settings", "Runtime configuration updated"),
    )
    conn.commit()
    conn.close()
    return settings()


async def _monitoring_loop():
    while True:
        try:
            cpu_series, cpu_error = prometheus_query(
                "sum(rate(container_cpu_usage_seconds_total[5m]))"
            )
            memory_series, memory_error = prometheus_query(
                "sum(container_memory_working_set_bytes)"
            )
            restart_series, restart_error = prometheus_query(
                "sum(kube_pod_container_status_restarts_total)"
            )
            if cpu_error is None and memory_error is None and restart_error is None:
                cpu = float(cpu_series[0]["value"][1]) if cpu_series else 0.0
                memory_bytes = float(memory_series[0]["value"][1]) if memory_series else 0.0
                restarts = float(restart_series[0]["value"][1]) if restart_series else 0.0
                analyse(AnalysisRequest(
                    cpu=round(cpu, 6),
                    memory=round(memory_bytes / (1024 ** 3), 6),
                    restarts=round(restarts, 3),
                ))
        except Exception as exc:
            conn = db()
            conn.execute(
                "INSERT INTO audit (timestamp,actor,action,details) VALUES (?,?,?,?)",
                (utcnow(), "monitoring", "Polling error", str(exc)),
            )
            conn.commit()
            conn.close()
        await asyncio.sleep(int(os.getenv("POLL_INTERVAL_SECONDS", "30")))

