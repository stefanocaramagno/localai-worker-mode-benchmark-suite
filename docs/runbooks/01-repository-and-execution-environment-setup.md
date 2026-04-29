# 01. Repository and Execution Environment Setup

## Objective

Prepare the local workstation and the repository working tree so that the project pipeline can be executed reliably, repeatably, and without environment-related ambiguity.

This runbook defines the required local tooling, the expected repository structure, the canonical execution entry points, the required file locations, and the minimum validation checks that must pass before any deployment, smoke validation, or benchmark phase begins.

---

## When to Execute

Execute this runbook in any of the following cases:

- before the first local execution of the project pipeline;
- after cloning or extracting a fresh copy of the repository;
- after changing workstation, shell environment, or Python environment;
- after updating local tooling such as `kubectl`, Python, or Locust;
- when baseline, sweep, validation, or post-processing scripts fail in a way that suggests a local environment issue.

This runbook should be treated as the canonical local setup reference for all subsequent runbooks.

---

## Scope

This runbook covers the local execution environment only. It includes:

- repository layout validation;
- required command-line tools;
- Python and Locust availability;
- shell execution assumptions for PowerShell and Bash;
- working-directory conventions;
- required configuration files and their canonical locations;
- minimum local checks that must pass before the cluster-facing workflow starts.

This runbook does **not** validate the Kubernetes cluster itself. Cluster validation is handled by the cluster bootstrap and pre-check workflows.

---

## Repository Root Assumption

All commands in this runbook assume that the current working directory is the repository root:

```text
localai-worker-mode-benchmark-suite/
```

The repository root is the anchor point used by the project scripts to resolve configuration files, Kubernetes manifests, load-test assets, and results directories.

Do not execute the main project scripts from arbitrary subdirectories unless the script explicitly supports it.

---

## Expected Repository Layout

At a minimum, the repository is expected to contain the following top-level directories and files:

```text
localai-worker-mode-benchmark-suite/
├── README.md
├── config/
├── docs/
├── infra/
├── load-tests/
├── results/
└── scripts/
```

The current pipeline depends in particular on the following locations:

```text
config/cluster-access/kubeconfig
config/scenarios/baseline/B0.json
config/precheck/TC1.json
config/phases/WM1.json
config/protocol/EP1.json
config/cluster-capture/CS1.json
config/metric-set/MS1.json
config/conventions/RC1.json
config/pilot-consolidation/CP1.json
config/statistical-rigor/SR1.json
config/technical-diagnosis/TD1.json
config/reporting/RP1.json
config/completion-gate/CG1.json
```

```text
infra/k8s/base/
infra/k8s/overlays/
infra/k8s/compositions/
```

```text
load-tests/locust/locustfile.py
```

```text
scripts/load/
scripts/validation/
scripts/analysis/
```

```text
results/
```

If any of these paths is missing, treat the repository as incomplete for pipeline execution.

---

## Required Local Tooling

The following tools must be available on the local workstation.

### Mandatory tools

- `kubectl`
- Python (documented as `python` for PowerShell and `python3` for Bash; if a Bash environment exposes only `python`, that is acceptable as long as the Bash scripts can resolve it)
- `locust`
- one supported shell:
  - PowerShell, or
  - Bash

### Strongly recommended tools

- `git`, if the repository is managed through version control locally;
- `unzip` or equivalent archive extraction utility, if the repository is distributed as a ZIP package;
- a code editor that preserves UTF-8 and LF/CRLF safely;
- OpenVPN client or equivalent, because the later runbooks require cluster access over VPN.

### Platform note

The project already provides both PowerShell and Bash entry points for the main execution phases. Use the shell family that best matches the workstation and keep the same shell family consistently throughout a given execution campaign whenever possible.

---

## Python and Locust Requirements

The current pipeline relies on Python for:

- Locust execution;
- analysis scripts under `scripts/analysis/`;
- shell-based helper logic that falls back to Python when parsing JSON or generating structured output.

Locust is required for:

- exploratory validation;
- baseline execution;
- pilot sweeps;
- consolidated pilot benchmark runs.

### Command convention used in the runbooks

To keep the documentation consistent across platforms, the runbooks use the following convention:

- PowerShell examples use `python`;
- Bash examples use `python3`;
- if a Unix-like environment exposes `python` instead of `python3`, that is acceptable as long as the Bash scripts can resolve a working Python interpreter.

This is a documentation convention. Where the repository launcher already resolves the Python interpreter automatically, prefer the launcher and do not call the underlying Python analysis script manually unless the runbook explicitly requires it.

### Minimum practical expectation

The local workstation must be able to run all of the following successfully:

#### PowerShell

```powershell
kubectl version --client
python --version
locust --version
```

#### Bash

```bash
kubectl version --client
python3 --version
locust --version
```

---

## Supported Execution Surfaces

The repository currently exposes two execution surfaces.

### PowerShell surface

Main entry points are provided through `.ps1` scripts, for example:

```text
scripts/load/baseline/Start-OfficialBaseline.ps1
scripts/load/exploratory/Start-LocustExploratory.ps1
scripts/load/pilot/Start-PilotWorkerCountSweep.ps1
scripts/load/pilot/Start-PilotWorkloadSweep.ps1
scripts/load/pilot/Start-PilotModelSweep.ps1
scripts/load/pilot/Start-PilotPlacementSweep.ps1
scripts/load/post/Start-ConsolidatedPilotBenchmarks.ps1
scripts/load/post/Start-TechnicalDiagnosis.ps1
scripts/load/post/Start-Reporting.ps1
scripts/load/post/Start-CompletionGate.ps1
```

Validation and collection entry points are also available in PowerShell:

```text
scripts/validation/precheck/Invoke-BenchmarkPrecheck.ps1
scripts/validation/precheck/Export-ValidationMetrics.ps1
scripts/validation/smoke/Test-LocalAIWorkerMode.ps1
scripts/validation/cluster-side/Collect-ClusterSideArtifacts.ps1
```

### Bash surface

Equivalent Bash entry points are also available, for example:

```text
scripts/load/baseline/start-official-baseline.sh
scripts/load/exploratory/start-locust-exploratory.sh
scripts/load/pilot/start-pilot-worker-count-sweep.sh
scripts/load/pilot/start-pilot-workload-sweep.sh
scripts/load/pilot/start-pilot-model-sweep.sh
scripts/load/pilot/start-pilot-placement-sweep.sh
scripts/load/post/start-consolidated-pilot-benchmarks.sh
scripts/load/post/start-technical-diagnosis.sh
scripts/load/post/start-reporting.sh
scripts/load/post/start-completion-gate.sh
```

Validation and collection entry points are also available in Bash:

```text
scripts/validation/precheck/invoke-benchmark-precheck.sh
scripts/validation/precheck/export-validation-metrics.sh
scripts/validation/smoke/test-localai-worker-mode.sh
scripts/validation/cluster-side/collect-cluster-side-artifacts.sh
```

---

## Canonical Configuration Files

The repository is driven by JSON configuration files that define the current baseline, execution protocol, collection scope, and post-processing rules.

The following files must exist and remain readable:

| File | Purpose |
|---|---|
| `config/scenarios/baseline/B0.json` | Official baseline definition. |
| `config/precheck/TC1.json` | Technical pre-check profile. |
| `config/phases/WM1.json` | Warm-up and measurement profile. |
| `config/protocol/EP1.json` | Standard execution protocol profile. |
| `config/cluster-capture/CS1.json` | Cluster-side evidence collection profile. |
| `config/metric-set/MS1.json` | Minimum client-side and cluster-side metric set. |
| `config/conventions/RC1.json` | Naming and run identification convention. |
| `config/pilot-consolidation/CP1.json` | Consolidated pilot benchmark profile. |
| `config/statistical-rigor/SR1.json` | Repeatability and statistical rigor profile. |
| `config/technical-diagnosis/TD1.json` | Technical diagnosis profile. |
| `config/reporting/RP1.json` | Reporting and visualization profile. |
| `config/completion-gate/CG1.json` | Completion gate profile. |
| `config/cluster-access/kubeconfig` | Project Kubernetes access file. |

These files are not optional metadata. They are live execution inputs used by the pipeline.

---

## Local Working Directory Conventions

Use the repository root as the working directory when launching the pipeline.

### Recommended practice

- open the shell in the repository root;
- reference the project `kubeconfig` explicitly;
- avoid using ad hoc relative paths from nested folders;
- keep paths stable across repeated runs.

### Example

#### PowerShell

```powershell
Set-Location C:\path\to\localai-worker-mode-benchmark-suite
```

#### Bash

```bash
cd /path/to/localai-worker-mode-benchmark-suite
```

This matters because many scripts resolve the repository root relative to their own file location and then expect the configuration tree and load-test assets to be present in their canonical locations.

---

## Local File and Directory Responsibilities

The following local paths have distinct roles and should not be confused.

### `config/`

Holds all configuration inputs used by the execution pipeline.

### `infra/`

Holds Kubernetes manifests, overlays, and compositions used to deploy the LocalAI server and RPC worker topologies.

### `load-tests/locust/`

Holds the Locust workload definition used by exploratory, baseline, and pilot benchmark phases.

### `scripts/`

Holds executable entry points and reusable shell/PowerShell helper libraries.

### `results/`

Holds benchmark outputs, validation summaries, cluster-side artifacts, and post-processing results.

The `results/` directory must exist before the pipeline is used. It does not need to be pre-populated, but the execution environment must have write access to it.

---

## Encoding and Line Ending Expectations

Use UTF-8 encoding for all Markdown, JSON, and script-adjacent configuration edits.

When working across Windows and Unix-like environments:

- preserve script executability where relevant;
- avoid introducing accidental line-ending changes in Bash scripts;
- avoid editing JSON files with tools that silently reformat or re-encode them in a way that breaks portability.

The safest approach is to use an editor that supports explicit UTF-8 and line-ending control.

---

## Environment Validation Procedure

Perform the following checks before using any pipeline script.

## Step 1 — Confirm repository completeness

From the repository root, verify that the key directories exist.

#### PowerShell

```powershell
Get-ChildItem
```

#### Bash

```bash
ls -la
```

### Expected outcome

You should see at least:

- `config`
- `docs`
- `infra`
- `load-tests`
- `results`
- `scripts`

If any of these are missing, stop and repair the local repository state.

---

## Step 2 — Confirm key execution files exist

Validate the core files that the pipeline expects.

#### PowerShell

```powershell
Test-Path .\config\scenarios\baseline\B0.json
Test-Path .\config\cluster-access\kubeconfig
Test-Path .\load-tests\locust\locustfile.py
Test-Path .\scripts\load\baseline\Start-OfficialBaseline.ps1
```

#### Bash

```bash
test -f ./config/scenarios/baseline/B0.json
test -f ./config/cluster-access/kubeconfig
test -f ./load-tests/locust/locustfile.py
test -f ./scripts/load/baseline/start-official-baseline.sh
```

### Expected outcome

All checks must resolve positively.

---

## Step 3 — Confirm shell-specific entry point availability

Validate that the chosen execution surface is present.

### PowerShell workflow

Check that these files exist:

```text
scripts/load/baseline/Start-OfficialBaseline.ps1
scripts/validation/precheck/Invoke-BenchmarkPrecheck.ps1
scripts/validation/smoke/Test-LocalAIWorkerMode.ps1
```

### Bash workflow

Check that these files exist:

```text
scripts/load/baseline/start-official-baseline.sh
scripts/validation/precheck/invoke-benchmark-precheck.sh
scripts/validation/smoke/test-localai-worker-mode.sh
```

### Expected outcome

The workstation has at least one complete execution surface available.

---

## Step 4 — Confirm Python availability

#### PowerShell

```powershell
python --version
```

#### Bash

```bash
python3 --version
```

If `python3` is not available on a Unix-like system but `python` is, validate it explicitly.

#### Bash alternative

```bash
python --version
```

### Expected outcome

A working Python interpreter is available.

---

## Step 5 — Confirm Locust availability

#### PowerShell

```powershell
locust --version
```

#### Bash

```bash
locust --version
```

### Expected outcome

Locust responds successfully from the active shell environment.

If not, install Locust in the active Python environment and re-run the check.

---

## Step 6 — Confirm `kubectl` availability

#### PowerShell

```powershell
kubectl version --client
```

#### Bash

```bash
kubectl version --client
```

### Expected outcome

The client version is returned without error.

This step validates the local binary only. Cluster reachability is validated in the cluster-related runbooks.

---

## Step 7 — Confirm write access to the results tree

#### PowerShell

```powershell
Test-Path .\results
```

#### Bash

```bash
test -d ./results
```

### Expected outcome

The `results/` directory exists and is writable.

If the directory is missing, create it or restore the repository state before proceeding.

---

## Optional Python Environment Strategy

The repository does not currently expose a dedicated environment manifest such as `requirements.txt`, `pyproject.toml`, or `Pipfile` at the root level. For this reason, the environment setup must currently be managed operationally.

### Recommended operational approach

- use a dedicated Python virtual environment for this project;
- install Locust into that environment;
- keep the environment stable throughout a benchmark campaign;
- do not mix multiple unrelated Python environments during the same execution phase.

### Example approach

#### PowerShell

```powershell
python -m venv .venv
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\.venv\Scripts\Activate.ps1"
pip install locust
```

#### Bash

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install locust
```

If a shared internal environment is already mandated by the delivery context, use that instead. The key requirement is consistency, not a specific toolchain.

---

## Recommended Local Readiness Checklist

Before moving to cluster-facing runbooks, confirm the following:

- the repository root is complete and correctly extracted or cloned;
- the shell starts from the repository root;
- `kubectl` is available;
- Python is available;
- Locust is available;
- the project `kubeconfig` exists at `config/cluster-access/kubeconfig`;
- the baseline and profile JSON files exist;
- the chosen shell surface has all required scripts;
- the workstation can write into `results/`.

If any item is not satisfied, do not proceed.

---

## Common Failure Modes

### 1. Running scripts from the wrong directory

Symptoms:

- file-not-found errors;
- baseline JSON not resolved;
- Locust file not found;
- output directories created in the wrong place.

Correction:

- return to the repository root;
- relaunch the command from there.

### 2. `locust` not found in `PATH`

Symptoms:

- baseline or pilot scripts fail before benchmark execution;
- shell reports command not found.

Correction:

- activate the intended Python environment;
- install Locust into that environment;
- validate `locust --version` again.

### 3. Python resolution mismatch between shells

Symptoms:

- Bash scripts fail to find `python3`;
- PowerShell resolves `python`, but Bash does not;
- the workstation mixes different Python commands across shell families without a clear convention.

Correction:

- standardize the active Python environment;
- follow the repository documentation convention (`python` in PowerShell, `python3` in Bash);
- if Bash exposes only `python`, make sure the Bash scripts can resolve it consistently before proceeding.

### 4. Missing configuration files after archive extraction

Symptoms:

- scripts fail immediately with JSON file not found errors.

Correction:

- verify the extracted repository contents;
- re-extract the repository package if necessary;
- confirm the configuration tree is intact.

### 5. Results directory not writable

Symptoms:

- scripts fail while exporting manifests, summaries, or benchmark artifacts.

Correction:

- verify local permissions;
- avoid running from read-only media or protected system directories.

---

## Exit Criteria

This runbook is complete only when all of the following are true:

1. the repository layout is complete and readable;
2. the required execution scripts are present;
3. `kubectl` is available locally;
4. Python is available locally;
5. Locust is available locally;
6. the project `kubeconfig` exists in its canonical path;
7. the `results/` directory is present and writable;
8. the workstation is ready to start the cluster-facing validation workflow.

At that point, proceed to the next runbook in sequence.

---

## Next Runbook

After this runbook is complete, continue with:

- `02-scenario-model-and-baseline-governance.md` for execution governance and experiment structure, if the repository model needs to be reviewed first; or
- the cluster-facing validation workflow, if repository and environment preparation are already complete and the next action is infrastructure access and pipeline execution.
