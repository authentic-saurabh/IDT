#!/usr/bin/env bash
set -euo pipefail
NAMESPACE="${HEALOPS_TEST_NAMESPACE:-default}"
kubectl run healops-memory-test --namespace "$NAMESPACE" --image=polinux/stress --restart=Never -- stress --vm 1 --vm-bytes 128M --timeout 180s
echo "Controlled memory test pod created. It requests approximately 128 MiB."
echo "Review Pod metrics before the 180-second test expires."
