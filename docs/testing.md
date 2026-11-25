# Testing

## Normal operation

Verify nodes, pods, and Prometheus series through the dashboard before injecting load.

## CPU anomaly

```bash
./test_cpu_anomaly.sh
```

## Memory anomaly

```bash
./test_memory_anomaly.sh
```

Wait at least for the configured baseline sample count before interpreting anomaly results.

## Pod failure

Set the test Deployment and namespace:

```bash
HEALOPS_TEST_NAMESPACE=default \
HEALOPS_TEST_DEPLOYMENT=my-test-deployment \
./test_pod_failure.sh
```

This is Kubernetes-native recovery unless HealOps explicitly executes a supported pod restart.

## AI-driven recovery

AI recovery is manual by default. Execute only from the Recovery API after confirming the Deployment owner, replica count, cooldown, and allowed namespace.
