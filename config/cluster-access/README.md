# Cluster access configuration

This directory contains the project kubeconfig used by the execution and validation scripts.

## Expected local file

The repository scripts expect the real Kubernetes client configuration at:

```text
config/cluster-access/kubeconfig
```

The real `kubeconfig` file is intentionally **not versioned** because it may contain sensitive cluster-access data.

## How to use this directory

1. Copy `kubeconfig.example` to `kubeconfig`.
2. Replace the placeholder content with the real kubeconfig provided for your environment.
3. Keep the real `kubeconfig` file only in your local working copy.

## Notes

- `kubeconfig.example` is a safe template only.
- The project scripts and runbooks continue to reference `config/cluster-access/kubeconfig` as the effective runtime path.
- If the real file is missing, commands that require cluster access will fail until it is restored locally.
