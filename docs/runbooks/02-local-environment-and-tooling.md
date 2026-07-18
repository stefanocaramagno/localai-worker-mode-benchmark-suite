# Local Environment and Tooling

## Purpose

This runbook defines the local workstation requirements needed to execute the LocalAI worker-mode benchmark suite from the repository root.

It covers:

1. required local tools;
2. supported shell surfaces;
3. Python and Locust setup;
4. Kubernetes client validation;
5. `proxmox-k3s` CLI availability;
6. Bash executable-bit handling;
7. local directory and write-permission checks;
8. environment readiness criteria before running cluster-facing workflows.

This runbook prepares the local execution environment only. Cluster access, kubeconfig handling, provider-local configuration, and secret-management rules are documented in `03-access-secrets-and-local-configuration.md`.

---

## Repository Root Assumption

All commands in this runbook must be executed from the repository root:

```text
localai-worker-mode-benchmark-suite/
```

The repository root is the anchor point for configuration files, Kubernetes manifests, Locust workloads, scripts, and generated artifacts.

### Windows PowerShell

```powershell
Get-ChildItem
```

### Bash

```bash
ls -la
```

A valid repository root contains at least:

```text
config/
docs/
infra/
load-tests/
scripts/
requirements.txt
```

The `results/` directory may be empty, partially populated, or absent before a clean regeneration. If it is absent, create it before starting any execution workflow.

---

## Local Tooling Matrix

The workstation must provide the tools listed below.

| Tool | Required | Used for |
|---|---:|---|
| PowerShell | Required on Windows | Windows execution surface for operational scripts. |
| Bash | Required on Linux/macOS/WSL/Git Bash | Unix-like execution surface for operational scripts. |
| Python | Required | Analysis scripts, provider-backed orchestration helpers, reporting, completion gates, freeze generation, and Locust environment management. |
| `pip` | Required | Installing Python dependencies from `requirements.txt`. |
| Locust | Required | Load generation for benchmark workloads. |
| `kubectl` | Required | Kubernetes access, deployment, validation, inspection, and artifact collection. |
| `kustomize` | Recommended; required for strict manifest rendering checks | Rendering Kubernetes compositions during static validation. |
| Helm | Required for C8 load-aware scheduler variants | Installing and validating the scheduler-plugins chart as a second scheduler. |
| `proxmox-k3s` | Required for provider-backed cycles | K3s cluster provisioning, kubeconfig retrieval, and cluster deletion on Proxmox-backed infrastructure. |
| Git | Recommended | Version-control validation, executable-bit preservation, and repository hygiene. |
| OpenVPN or equivalent VPN client | Environment-dependent | Required when the target Kubernetes or Proxmox environment is reachable only through a private network. |
| Go toolchain | Optional | Needed only when building the `proxmox-k3s` CLI from source instead of using an existing binary. |

The benchmark suite does not require a local Docker daemon for the normal documented execution path, unless a future local-only workflow explicitly adds that requirement.

---

## Shell Surface Convention

The repository exposes two operational surfaces:

1. Windows PowerShell scripts with `.ps1` entry points;
2. Bash scripts with `.sh` entry points.

Use one shell family consistently within the same execution run whenever possible. Mixing shells during a single run can make troubleshooting more difficult, especially when local paths, virtual environments, environment variables, and executable-bit behavior differ.

### Windows PowerShell

```powershell
$PSVersionTable.PSVersion
```

### Bash

```bash
printf '%s\n' "$BASH_VERSION"
```

Both commands should return a shell version without error.

---

## Recommended Local Directory Layout

The benchmark suite repository and the `proxmox-k3s` provider repository may be kept as sibling directories.

Example layout:

```text
workspace/
├── localai-worker-mode-benchmark-suite/
└── proxmox-k3s/
```

This layout is not mandatory, but it keeps benchmark-suite execution and provider-tool maintenance clearly separated.

When using a provider binary outside the system `PATH`, pass its explicit path to provider-backed scripts. Provider-specific usage is documented in `04-proxmox-k3s-provider-lifecycle.md`.

---

## Validate the Repository Root

Run the following checks from the repository root.

### Windows PowerShell

```powershell
Test-Path .\config
Test-Path .\docs
Test-Path .\infra
Test-Path .\load-tests
Test-Path .\scripts
Test-Path .\requirements.txt
```

### Bash

```bash
test -d ./config
test -d ./docs
test -d ./infra
test -d ./load-tests
test -d ./scripts
test -f ./requirements.txt
```

All checks must evaluate successfully. If any path is missing, stop and repair the local repository state before continuing.

---

## Validate Core Execution Entrypoints

The repository must expose both PowerShell and Bash entry points for the main execution families.

### Windows PowerShell

```powershell
Test-Path .\scripts\experimental-cycles\Start-ExperimentalCycle.ps1
Test-Path .\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1
Test-Path .\scripts\infrastructure\provision\Start-ProviderBackedProvisioning.ps1
Test-Path .\scripts\infrastructure\validation\Start-ProviderBackedClusterValidation.ps1
Test-Path .\scripts\application\deployment\Start-ProviderBackedLocalAIDeployment.ps1
Test-Path .\scripts\load\baseline\Start-OfficialBaseline.ps1
Test-Path .\scripts\validation\smoke\Test-LocalAIWorkerMode.ps1
Test-Path .\scripts\load\post\Start-TechnicalDiagnosis.ps1
Test-Path .\scripts\load\post\Start-Reporting.ps1
Test-Path .\scripts\load\post\Start-CompletionGate.ps1
Test-Path .\scripts\load\post\Start-FreezeExperimentalCycle.ps1
```

### Bash

```bash
test -f ./scripts/experimental-cycles/start-experimental-cycle.sh
test -f ./scripts/experimental-cycles/start-experimental-campaign.sh
test -f ./scripts/infrastructure/provision/start-provider-backed-provisioning.sh
test -f ./scripts/infrastructure/validation/start-provider-backed-cluster-validation.sh
test -f ./scripts/application/deployment/start-provider-backed-localai-deployment.sh
test -f ./scripts/load/baseline/start-official-baseline.sh
test -f ./scripts/validation/smoke/test-localai-worker-mode.sh
test -f ./scripts/load/post/start-technical-diagnosis.sh
test -f ./scripts/load/post/start-reporting.sh
test -f ./scripts/load/post/start-completion-gate.sh
test -f ./scripts/load/post/start-freeze-experimental-cycle.sh
```

All checks must succeed before using the execution runbooks.

---

## Python Setup Strategy

Use a dedicated Python virtual environment for the benchmark suite. This keeps Locust and supporting Python execution isolated from unrelated workstation packages.

The repository contains a `requirements.txt` file. Install dependencies from that file instead of installing tools manually one by one.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

### Bash

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r ./requirements.txt
```

After installation, either activate the virtual environment or invoke Python and Locust through the virtual-environment paths.

### Windows PowerShell

```powershell
.\.venv\Scripts\Activate.ps1
```

### Bash

```bash
source ./.venv/bin/activate
```

If the PowerShell activation command is blocked by local execution policy, use the direct `.venv` Python path for installation and validation commands, or start script execution with `-ExecutionPolicy Bypass` as shown in the operational runbooks.

---

## Python and Locust Validation

Validate that Python and Locust resolve from the active environment.

### Windows PowerShell

```powershell
python --version
python -m pip --version
locust --version
```

### Bash

```bash
python3 --version
python3 -m pip --version
locust --version
```

If the active Bash environment exposes `python` instead of `python3`, validate it explicitly.

### Windows PowerShell

```powershell
python --version
```

### Bash

```bash
python --version
```

The command used by the selected shell must resolve consistently throughout the run.

---

## Validate the Installed Requirements

The dependency installation is valid only if the packages from `requirements.txt` are available from the same Python environment used by the runbooks.

### Windows PowerShell

```powershell
python -m pip show locust
```

### Bash

```bash
python3 -m pip show locust
```

The command must return package metadata for Locust. If it does not, activate the intended virtual environment and reinstall the repository requirements.

---

## Kubernetes CLI Validation

The local workstation must provide `kubectl`. This runbook validates the client only. Cluster reachability is validated later, using explicit kubeconfig files.

### Windows PowerShell

```powershell
kubectl version --client
```

### Bash

```bash
kubectl version --client
```

The command must return the client version without error.

Do not rely on the default Kubernetes context for benchmark execution. Later runbooks use explicit kubeconfig paths for fixed-cluster and provider-backed workflows.

---

## Optional Kustomize Validation

The benchmark suite deploys Kubernetes resources from manifests and Kustomize-style directory structures. A standalone `kustomize` binary is not mandatory when the required functionality is available through `kubectl`.

### Windows PowerShell

```powershell
kubectl kustomize .\infra\k8s\compositions\foundation\namespace
```

### Bash

```bash
kubectl kustomize ./infra/k8s/compositions/foundation/namespace
```

The command should render Kubernetes YAML or fail with a repository-path issue that must be corrected before deployment. This command does not apply resources to a cluster.

---

## `proxmox-k3s` CLI Availability

Provider-backed cycles require access to the `proxmox-k3s` CLI.

If the binary is already in `PATH`, validate it directly.

### Windows PowerShell

```powershell
proxmox-k3s --help
```

### Bash

```bash
proxmox-k3s --help
```

If the binary is stored outside `PATH`, validate the explicit path. Adjust the path to match the local workstation.

### Windows PowerShell

```powershell
..\proxmox-k3s\bin\proxmox-k3s.exe --help
```

### Bash

```bash
../proxmox-k3s/bin/proxmox-k3s --help
```

On Windows, the provider repository may expose `proxmox-k3s.exe`. On Unix-like systems, use the platform-specific executable built or downloaded for that system.

Provider-backed runbooks can pass this executable through their `ToolPath` or `--tool-path` argument.

---

## Optional Provider Build Validation

Building `proxmox-k3s` from source is optional. Use this only if a suitable binary is not already available.

From the `proxmox-k3s` repository root, validate the Go toolchain.

### Windows PowerShell

```powershell
go version
```

### Bash

```bash
go version
```

Build the provider CLI only when needed.

### Windows PowerShell

```powershell
go build -o .\bin\proxmox-k3s.exe .\cmd\main.go
```

### Bash

```bash
go build -o ./bin/proxmox-k3s ./cmd/main.go
```

After building, re-run the `proxmox-k3s --help` validation using either `PATH` resolution or the explicit binary path.

---

## VPN and Private-Network Access

Some fixed-cluster and provider-backed workflows may require a VPN or equivalent private-network connection. VPN setup is environment-specific and is not configured by the benchmark suite.

Validate that the VPN client is available when the target environment requires it.

### Windows PowerShell

```powershell
Get-Command openvpn -ErrorAction SilentlyContinue
```

### Bash

```bash
command -v openvpn || true
```

If no command is returned but a graphical VPN client is used, validate VPN connectivity through the cluster-access runbook instead of relying on this command.

---

## Bash Executable Bits

Bash scripts must have executable permissions in Unix-like environments. The repository includes maintenance scripts to restore executable bits.

Run the maintenance command after extracting the repository from a ZIP archive, after moving the repository across filesystems, or whenever Bash scripts fail with a permission error.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\maintenance\Set-BashExecutableBits.ps1 -SkipGitIndex
```

### Bash

```bash
bash ./scripts/maintenance/set-bash-executable-bits.sh --skip-git-index
```

If the repository is inside a Git working tree and executable-bit metadata must be preserved in the Git index, omit the skip option.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\maintenance\Set-BashExecutableBits.ps1
```

### Bash

```bash
bash ./scripts/maintenance/set-bash-executable-bits.sh
```

---

## Validate Generated-Artifact Write Access

The benchmark suite writes regenerated artifacts under `results/`. Ensure the directory exists and is writable.

### Windows PowerShell

```powershell
New-Item -ItemType Directory -Force .\results | Out-Null
New-Item -ItemType Directory -Force .\results\_runtime | Out-Null
"write-test" | Set-Content .\results\_runtime\local-write-test.txt
Remove-Item .\results\_runtime\local-write-test.txt
```

### Bash

```bash
mkdir -p ./results/_runtime
printf '%s\n' "write-test" > ./results/_runtime/local-write-test.txt
rm ./results/_runtime/local-write-test.txt
```

The commands must complete without permission errors.

---

## Validate Documentation Set Continuity

The local documentation set should contain the complete runbook sequence.

### Windows PowerShell

```powershell
$Runbooks = @(
  ".\docs\runbooks\00-runbooks-index.md",
  ".\docs\runbooks\01-execution-model-and-repository-map.md",
  ".\docs\runbooks\02-local-environment-and-tooling.md",
  ".\docs\runbooks\03-access-secrets-and-local-configuration.md",
  ".\docs\runbooks\04-proxmox-k3s-provider-lifecycle.md",
  ".\docs\runbooks\05-configuration-model-and-cycle-taxonomy.md",
  ".\docs\runbooks\06-fixed-cluster-c0-execution.md",
  ".\docs\runbooks\07-provider-backed-c1-baseline-execution.md",
  ".\docs\runbooks\08-provider-backed-c2-c6-campaign-execution.md",
  ".\docs\runbooks\09-default-scheduler-c7-baseline-execution.md",
  ".\docs\runbooks\10-resource-aware-scheduler-c8-execution.md",
  ".\docs\runbooks\11-network-aware-scheduler-c9-execution.md",
  ".\docs\runbooks\12-localai-deployment-topologies-and-placement.md",
  ".\docs\runbooks\13-load-generation-observability-and-artifacts.md",
  ".\docs\runbooks\14-diagnosis-reporting-completion-gate-and-freeze.md",
  ".\docs\runbooks\15-results-cleanup-and-full-regeneration.md",
  ".\docs\runbooks\16-troubleshooting-and-recovery.md",
  ".\docs\runbooks\17-command-reference.md"
)
foreach ($Runbook in $Runbooks) {
  if (-not (Test-Path $Runbook)) {
    throw "Missing runbook: $Runbook"
  }
}
```

### Bash

```bash
runbooks=(
  "./docs/runbooks/00-runbooks-index.md"
  "./docs/runbooks/01-execution-model-and-repository-map.md"
  "./docs/runbooks/02-local-environment-and-tooling.md"
  "./docs/runbooks/03-access-secrets-and-local-configuration.md"
  "./docs/runbooks/04-proxmox-k3s-provider-lifecycle.md"
  "./docs/runbooks/05-configuration-model-and-cycle-taxonomy.md"
  "./docs/runbooks/06-fixed-cluster-c0-execution.md"
  "./docs/runbooks/07-provider-backed-c1-baseline-execution.md"
  "./docs/runbooks/08-provider-backed-c2-c6-campaign-execution.md"
  "./docs/runbooks/09-default-scheduler-c7-baseline-execution.md"
  "./docs/runbooks/10-resource-aware-scheduler-c8-execution.md"
  "./docs/runbooks/11-network-aware-scheduler-c9-execution.md"
  "./docs/runbooks/12-localai-deployment-topologies-and-placement.md"
  "./docs/runbooks/13-load-generation-observability-and-artifacts.md"
  "./docs/runbooks/14-diagnosis-reporting-completion-gate-and-freeze.md"
  "./docs/runbooks/15-results-cleanup-and-full-regeneration.md"
  "./docs/runbooks/16-troubleshooting-and-recovery.md"
  "./docs/runbooks/17-command-reference.md"
)
for runbook in "${runbooks[@]}"; do
  test -f "$runbook" || { echo "Missing runbook: $runbook" >&2; exit 1; }
done
```

Both checks should succeed after the documentation tree has been copied into the repository.

---

## Encoding and Line-Ending Requirements

Use UTF-8 for Markdown, JSON, YAML, Python, PowerShell, and Bash files.

Follow the repository line-ending policy:

1. Bash scripts must keep LF line endings.
2. PowerShell scripts are LF-normalized for consistent diffs.
3. Markdown, JSON, YAML, CSV, TXT, and HTML files are LF-normalized.
4. Binary files must not be line-ending normalized.

Do not use editors that silently rewrite line endings or encodings across the entire repository.

Validate Git line-ending metadata when Git is available.

### Windows PowerShell

```powershell
git status --short
```

### Bash

```bash
git status --short
```

Unexpected changes in many scripts or configuration files may indicate accidental line-ending rewrites.

---

## Local Environment Variables

Most workflows can be executed with explicit command arguments and repository configuration files. Environment variables are optional and should not replace documented configuration paths.

When a provider binary is outside `PATH`, it can be convenient to define a local shell variable for the current session.

### Windows PowerShell

```powershell
$ProxmoxK3sTool = "..\proxmox-k3s\bin\proxmox-k3s.exe"
& $ProxmoxK3sTool --help
```

### Bash

```bash
PROXMOX_K3S_TOOL="../proxmox-k3s/bin/proxmox-k3s"
"$PROXMOX_K3S_TOOL" --help
```

The variable name is a local shell convenience only. The provider-backed runbooks still pass the tool path explicitly when required.

---

## Local Readiness Checklist

Before moving to the access and configuration runbook, verify that all items below are satisfied.

| Check | Required outcome |
|---|---|
| Repository root | `config/`, `docs/`, `infra/`, `load-tests/`, `scripts/`, and `requirements.txt` are present. |
| Python | A working interpreter is available from the selected shell. |
| Python packages | `requirements.txt` has been installed into the intended environment. |
| Locust | `locust --version` works from the selected shell. |
| Kubernetes CLI | `kubectl version --client` works. |
| Provider CLI | `proxmox-k3s --help` or an explicit provider binary path works when provider-backed cycles will be executed. |
| Bash permissions | Bash scripts have executable bits restored when running in Unix-like environments. |
| Results directory | `results/` exists and is writable. |
| Documentation continuity | `00-runbooks-index.md` and `01-execution-model-and-repository-map.md` are present in `docs/runbooks/`. |

---

## Common Local Failures and Corrections

### Python resolves to the wrong environment

Symptoms:

1. `locust` is not found;
2. `python -m pip show locust` does not show the expected package;
3. scripts work in one shell but fail in another.

Correction:

1. activate the intended virtual environment;
2. reinstall dependencies from `requirements.txt`;
3. rerun the Python and Locust validation commands.

### PowerShell blocks script execution

Symptoms:

1. `.ps1` scripts fail before running;
2. activation of `.venv` fails with an execution-policy message.

Correction:

Use explicit script execution with `-ExecutionPolicy Bypass` when invoking documented PowerShell entry points.

### Bash scripts fail with permission denied

Symptoms:

1. `.sh` entry points exist but cannot be executed directly;
2. archive extraction removed executable bits.

Correction:

Run the Bash executable-bit maintenance command documented above.

### `kubectl` exists but cluster commands fail

Symptoms:

1. `kubectl version --client` works;
2. `kubectl get nodes` fails.

Correction:

This runbook validates only the local client. Continue with `03-access-secrets-and-local-configuration.md` to validate explicit kubeconfig paths and private-network access.

### `proxmox-k3s` is not found

Symptoms:

1. provider-backed provisioning scripts fail before creating or inspecting a cluster;
2. the shell cannot resolve `proxmox-k3s`.

Correction:

Use an explicit provider binary path through `ToolPath` or `--tool-path`, or place the provider binary in `PATH` and rerun the provider CLI validation.

---

## Exit Criteria

This runbook is complete when:

1. the repository root has been validated;
2. the selected shell surface is available;
3. Python is available;
4. repository Python requirements are installed;
5. Locust is available;
6. `kubectl` is available;
7. `proxmox-k3s` is available or its explicit path is known for provider-backed cycles;
8. Bash executable-bit handling has been verified when Bash will be used;
9. `results/` is writable;
10. the local documentation set is continuous.

After these criteria are satisfied, continue with:

```text
03-access-secrets-and-local-configuration.md
```
