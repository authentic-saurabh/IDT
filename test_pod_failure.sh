#!/usr/bin/env bash
set -euo pipefail
NAMESPACE="${HEALOPS_TEST_NAMESPACE:-default}"
DEPLOYMENT="${HEALOPS_TEST_DEPLOYMENT:-}"

if [[ -z "$DEPLOYMENT" ]]; then
  echo "Set HEALOPS_TEST_DEPLOYMENT to a test Deployment name."
  exit 1
fi

POD=$(kubectl get pods -n "$NAMESPACE" -l "app=$DEPLOYMENT" -o jsonpath='{.items[0].metadata.name}')
[[ -n "$POD" ]] || { echo "No matching pod found"; exit 1; }
kubectl delete pod -n "$NAMESPACE" "$POD" --wait=false
echo "Deleted $POD. Kubernetes-native replacement will be recorded only if you confirm replacement pod health."
