#!/usr/bin/env bash
set -euo pipefail
NAMESPACE="${HEALOPS_TEST_NAMESPACE:-default}"
kubectl run healops-cpu-test --namespace "$NAMESPACE" --image=polinux/stress --restart=Never -- stress --cpu 1 --timeout 180s
echo "Controlled CPU test pod created in namespace $NAMESPACE."
echo "Inspect metrics in Prometheus for at least 2 minutes, then run:"
echo "curl -X POST http://localhost:8000/api/ai/analyse -H 'Content-Type: application/json' -d '{\"cpu\":95,\"memory\":60,\"restarts\":0}'"
