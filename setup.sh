#!/usr/bin/env bash
set -euo pipefail

command -v docker >/dev/null || { echo "Docker is required"; exit 1; }
command -v kind >/dev/null || { echo "Kind is required"; exit 1; }
command -v kubectl >/dev/null || { echo "kubectl is required"; exit 1; }

if ! kind get clusters | grep -qx healops; then
  kind create cluster --name healops --config infrastructure/kind-cluster.yaml
fi

kubectl apply -f infrastructure/namespace.yaml
kubectl apply -f infrastructure/rbac.yaml

if command -v helm >/dev/null; then
  helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
  helm repo update >/dev/null 2>&1 || true
  helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
    --namespace monitoring --create-namespace \
    --set grafana.adminPassword=admin \
    --set grafana.service.type=NodePort \
    --set prometheus.service.type=NodePort
else
  echo "Helm is not installed; Docker Compose monitoring remains optional."
fi

echo "HealOps services started."
echo "Frontend: cd frontend && npm install && npm run dev"
