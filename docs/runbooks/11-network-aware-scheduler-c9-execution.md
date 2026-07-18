# Network-Aware Scheduler C9 Execution

## Purpose

This runbook documents the `C9` network-aware scheduler campaign.

`C9` compares three scheduler modes for distributed LocalAI worker-mode workloads:

1. Kubernetes default scheduling;
2. a resource-aware custom scheduler using `LoadAwareResourcesBalancedAllocation`;
3. a resource plus network-aware custom scheduler using `LoadAwareResourcesBalancedAllocation` together with `NetworkAwareLocalAi`.

The campaign is provider-backed, gateway-routed, multi-tenant, telemetry-aware, and designed to evaluate whether network-aware placement becomes relevant when tenant traffic differs and the inter-node network topology is no longer uniform.

The purpose of this runbook is to provide an operational procedure for:

1. validating the C9 network-aware configuration set;
2. validating the provider-backed four-worker infrastructure profile and provider binding;
3. validating the LocalAI scheduler-mode and network-aware Kubernetes manifests;
4. validating Istio gateway-routed traffic as the official benchmark access path;
5. validating `mon-agent` and Mentat as the annotation and inter-node telemetry sources;
6. installing and validating the custom scheduler for load-aware and network-aware variants;
7. executing the default, load-aware, and network-aware variants as a single controlled campaign;
8. inspecting gateway, annotation, Mentat, scheduler, rescheduling, benchmark, diagnosis, reporting, completion-gate, and freeze evidence.

`C9` must be interpreted as a network-aware scheduler campaign, not as a replacement for `C8`. `C8` remains the resource-aware comparison. `C9` extends the comparison by adding gateway-routed traffic, inter-node network telemetry, network-aware annotation evidence, and the `NetworkAwareLocalAi` scheduler plugin.

---

## Repository Root Assumption

All commands assume that the current working directory is the repository root:

```text
localai-worker-mode-benchmark-suite/
```

### Windows PowerShell

```powershell
Set-Location C:\Path\To\localai-worker-mode-benchmark-suite
Get-Location
```

### Bash

```bash
cd /path/to/localai-worker-mode-benchmark-suite
pwd
```

---

## C9 Execution Model

The C9 execution flow is:

```text
C9.json
-> network-aware-scheduler scenario index
-> 42 scheduler-mode scenario profiles
-> 4-worker provider-backed infrastructure profile and provider binding
-> proxmox-k3s cluster lifecycle with monitoring, mon-agent, cluster-lens, Mentat, and Istio add-ons
-> provider-backed cluster validation
-> scheduler-mode manifest validation
-> LocalAI tenant deployment with group/app/role labels
-> Istio Gateway and VirtualService validation
-> mon-agent validation and deployment annotation validation
-> Mentat network observability validation
-> latency profile application or annotation-controlled latency matrix validation
-> custom scheduler installation for LOADAWARE and NETAWARE variants
-> gateway-routed telemetry priming
-> telemetry-gated controlled redeployment when required
-> scheduler decision capture
-> cluster-lens placement capture at configured pipeline stages
-> official benchmark measurement window
-> minimal observability capture
-> technical diagnosis
-> comparative reporting
-> completion gate
-> freeze
```

The campaign is executed through the campaign runner, not by directly executing `C9.json` as a single provider-backed cycle.

Canonical C9 campaign entry points:

```text
scripts/experimental-cycles/Start-ExperimentalCampaign.ps1
scripts/experimental-cycles/start-experimental-campaign.sh
scripts/experimental-cycles/run-experimental-campaign.py
```

Canonical C9 cycle profile:

```text
config/experimental-cycles/C9.json
```

---

## Methodological Boundary

C9 is a resource plus network-aware scheduler campaign.

It must preserve the following boundaries:

| Boundary | C9 rule |
|---|---|
| Scheduler-mode coverage | Each logical scenario is executed under `DEFAULT`, `LOADAWARE`, and `NETAWARE` variants. |
| Default scheduler variant | `spec.schedulerName` must be absent from LocalAI workloads. |
| Load-aware variant | `spec.schedulerName` must be `scheduler-plugins-scheduler` and the scheduler profile must enable `LoadAwareResourcesBalancedAllocation`. |
| Network-aware variant | `spec.schedulerName` must be `scheduler-plugins-scheduler` and the scheduler profile must enable both `LoadAwareResourcesBalancedAllocation` and `NetworkAwareLocalAi`. |
| Runtime telemetry | CPU, memory, gateway-traffic, deployment traffic, inter-node latency, packet loss, and bandwidth evidence must be captured when the scenario requires it. |
| Gateway traffic source | Gateway-routed tenant traffic is the official proxy for tenant intensity. |
| Access path | The official benchmark access path is Istio Gateway to VirtualService to LocalAI Service to LocalAI master pod. |
| Monitoring agent | `mon-agent` is the runtime annotation source. |
| Network telemetry | Mentat is the inter-node network telemetry source. |
| Placement evidence | cluster-lens and Kubernetes snapshots preserve the placement used to interpret each scheduler-mode variant. |
| Workload labels | LocalAI workloads must expose `group`, `app`, and plain `role` labels consistently. |
| Latency topology | C9 uses `L0`, `L1`, `L2`, and `L3` latency semantics; `L1`, `L2`, and `L3` annotation-controlled profiles must be visible to scheduler-facing annotations before the relevant placement decision. |
| Autoscaling | Autoscaling is out of scope for C9. |
| Placement controls | Hard pod placement controls must not be used to predetermine LocalAI placement. |
| Measurement boundary | Telemetry priming, annotation refresh, controlled redeployment, readiness waiting, and stabilization are excluded from the official measurement window. |

The network-aware conclusion must be scenario-dependent. C9 must not be interpreted as proving that network-aware scheduling always improves latency or throughput. It evaluates whether the placement logic becomes more suitable when network cost is observable and discriminating.

---

## Canonical C9 Inputs

| Input family | Canonical path |
|---|---|
| Cycle profile | `config/experimental-cycles/C9.json` |
| Scenario index | `config/scenarios/network-aware-scheduler/NETWORK_AWARE_SCHEDULER_SCENARIOS_INDEX.json` |
| Scenario profiles | `config/scenarios/network-aware-scheduler/NA_*.json` |
| Scheduler integration index | `config/scheduler/SCHEDULER_INTEGRATION_INDEX.json` |
| Load-aware scheduler profile | `config/scheduler/profiles/CS_C9_LOADAWARE_SECOND_SCHEDULER.json` |
| Resource plus network-aware scheduler profile | `config/scheduler/profiles/CS_C9_LOCALAI_RESOURCE_NETWORK_AWARE_SECOND_SCHEDULER.json` |
| mon-agent index | `config/mon-agent/MON_AGENT_INDEX.json` |
| mon-agent profile | `config/mon-agent/profiles/MA_NETWORK_AWARE.json` |
| Network observability index | `config/network-observability/NETWORK_OBSERVABILITY_INDEX.json` |
| Mentat profile | `config/network-observability/profiles/NO_MENTAT_C9.json` |
| Istio gateway index | `config/istio-gateway/ISTIO_GATEWAY_INDEX.json` |
| Istio gateway profile | `config/istio-gateway/profiles/IG_LOCALAI_GATEWAY_ROUTED_C9.json` |
| cluster-lens index | `config/cluster-lens/CLUSTER_LENS_INDEX.json` |
| cluster-lens capture profile | `config/cluster-lens/profiles/CL_C9_PLACEMENT_SNAPSHOT.json` |
| cluster-lens collectors | `scripts/observability/cluster-lens/capture-cluster-lens-snapshot.py`, `scripts/observability/cluster-lens/Capture-ClusterLensSnapshot.ps1`, `scripts/observability/cluster-lens/capture-cluster-lens-snapshot.sh` |
| Rescheduling index | `config/rescheduling/RESCHEDULING_INDEX.json` |
| Rescheduling profile | `config/rescheduling/profiles/RS_C9_NETWORK_AWARE_TELEMETRY_PRIMED_REDEPLOYMENT.json` |
| Infrastructure profile | `config/infrastructure/profiles/INFRA_C9_1CP_4W_8C16G.json` |
| Provider binding | `config/infrastructure/providers/proxmox-k3s/bindings/BINDING_INFRA_C9_1CP_4W_8C16G_PROXMOX_K3S.json` |
| Provider local YAML | `config/infrastructure/providers/proxmox-k3s/local/cluster.c9-1cp-4w-8c16g.local.yaml` |
| Network-aware Kubernetes manifests | `infra/k8s/compositions/network-aware-scheduler/` |
| Manifest validator | `scripts/validation/scheduler/validate-scheduler-mode-manifests.py` |
| Istio validator | `scripts/istio/validate-istio-gateway.py` |
| Mentat validator | `scripts/network-observability/validate-mentat.py` |
| Technical diagnosis profile | `config/technical-diagnosis/profiles/TD_C9_NETWORK_AWARE_SCHEDULER.json` |
| Reporting profile | `config/reporting/profiles/RP_C9_NETWORK_AWARE_SCHEDULER.json` |
| Completion gate profile | `config/completion-gate/profiles/CG_C9_NETWORK_AWARE_SCHEDULER.json` |
| Freeze profile | `config/freeze/profiles/FR_C9_NETWORK_AWARE_SCHEDULER.json` |

---

## Canonical C9 Output Roots

| Artifact family | Canonical root |
|---|---|
| Campaign execution manifests | `results/experimental-cycles/C9/execution/` |
| Generated runtime configs | `results/experimental-cycles/C9/execution/generated-runtime-configs/` |
| Benchmark outputs | `results/experimental-cycles/C9/benchmark/network-aware-scheduler/` |
| Scheduler decision evidence | `results/experimental-cycles/C9/scheduler/` |
| Custom scheduler evidence | `results/experimental-cycles/C9/scheduler/custom-scheduler/` |
| Per-variant runtime evidence | `results/experimental-cycles/C9/variants/<variant-id>/` |
| Minimal observability | `results/experimental-cycles/C9/variants/<variant-id>/observability/minimal/` |
| mon-agent evidence | `results/experimental-cycles/C9/variants/<variant-id>/network-aware-scheduler/mon-agent/` |
| Mentat evidence | `results/experimental-cycles/C9/variants/<variant-id>/network-aware-scheduler/mentat/` |
| Istio evidence | `results/experimental-cycles/C9/variants/<variant-id>/network-aware-scheduler/istio/` |
| cluster-lens placement evidence | `results/experimental-cycles/C9/variants/<variant-id>/network-aware-scheduler/cluster-lens/` |
| Telemetry priming evidence | `results/experimental-cycles/C9/variants/<variant-id>/network-aware-scheduler/telemetry-priming/` |
| Rescheduling evidence | `results/experimental-cycles/C9/variants/<variant-id>/network-aware-scheduler/rescheduling/` |
| Technical diagnosis | `results/experimental-cycles/C9/diagnosis/` |
| Reporting | `results/experimental-cycles/C9/reporting/` |
| Completion gate | `results/experimental-cycles/C9/completion-gate/` |
| Freeze | `results/experimental-cycles/C9/freeze/` |
| Frozen snapshot | `results/experimental-cycles/C9/artifacts/` |

Generated artifacts under `results/` may be removed and regenerated. They should not be edited manually.

C9 does not require a dedicated Chaos Mesh artifact root for final interpretation. Latency-differentiated scenarios are interpreted through the declared latency profiles, scheduler-facing annotations, Mentat evidence, rescheduling evidence, and cluster-lens placement evidence.

---

## C9 Scenario Matrix

C9 contains fourteen logical scenarios. Each logical scenario is executed in three variants:

```text
DEFAULT
LOADAWARE
NETAWARE
```

The planned campaign therefore contains forty-two variants. With the default replica set `A,B,C`, a complete campaign produces one hundred and twenty-six benchmark runs.

| Priority | Logical scenario | Default variant | Load-aware variant | Network-aware variant |
|---|---|---|---|---|
| `P0` | `2T_4N_L0_UNIFORM_M1M1_W2` | `NA_DEFAULT_2T_4N_L0_UNIFORM_M1M1_W2` | `NA_LOADAWARE_2T_4N_L0_UNIFORM_M1M1_W2` | `NA_NETAWARE_2T_4N_L0_UNIFORM_M1M1_W2` |
| `P0` | `2T_4N_L0_DIFFERENTIATED_M1M1_W2` | `NA_DEFAULT_2T_4N_L0_DIFFERENTIATED_M1M1_W2` | `NA_LOADAWARE_2T_4N_L0_DIFFERENTIATED_M1M1_W2` | `NA_NETAWARE_2T_4N_L0_DIFFERENTIATED_M1M1_W2` |
| `P0` | `2T_4N_L1_UNIFORM_M1M1_W2` | `NA_DEFAULT_2T_4N_L1_UNIFORM_M1M1_W2` | `NA_LOADAWARE_2T_4N_L1_UNIFORM_M1M1_W2` | `NA_NETAWARE_2T_4N_L1_UNIFORM_M1M1_W2` |
| `P0` | `2T_4N_L1_DIFFERENTIATED_M1M1_W2` | `NA_DEFAULT_2T_4N_L1_DIFFERENTIATED_M1M1_W2` | `NA_LOADAWARE_2T_4N_L1_DIFFERENTIATED_M1M1_W2` | `NA_NETAWARE_2T_4N_L1_DIFFERENTIATED_M1M1_W2` |
| `P0` | `2T_4N_L2_UNIFORM_M1M1_W2` | `NA_DEFAULT_2T_4N_L2_UNIFORM_M1M1_W2` | `NA_LOADAWARE_2T_4N_L2_UNIFORM_M1M1_W2` | `NA_NETAWARE_2T_4N_L2_UNIFORM_M1M1_W2` |
| `P0` | `2T_4N_L2_DIFFERENTIATED_M1M1_W2` | `NA_DEFAULT_2T_4N_L2_DIFFERENTIATED_M1M1_W2` | `NA_LOADAWARE_2T_4N_L2_DIFFERENTIATED_M1M1_W2` | `NA_NETAWARE_2T_4N_L2_DIFFERENTIATED_M1M1_W2` |
| `P1` | `1T_4N_L0_UNIFORM_M1_W2` | `NA_DEFAULT_1T_4N_L0_UNIFORM_M1_W2` | `NA_LOADAWARE_1T_4N_L0_UNIFORM_M1_W2` | `NA_NETAWARE_1T_4N_L0_UNIFORM_M1_W2` |
| `P1` | `1T_4N_L2_UNIFORM_M1_W2` | `NA_DEFAULT_1T_4N_L2_UNIFORM_M1_W2` | `NA_LOADAWARE_1T_4N_L2_UNIFORM_M1_W2` | `NA_NETAWARE_1T_4N_L2_UNIFORM_M1_W2` |
| `P1` | `2T_4N_L1_DIFFERENTIATED_M1M2_W2` | `NA_DEFAULT_2T_4N_L1_DIFFERENTIATED_M1M2_W2` | `NA_LOADAWARE_2T_4N_L1_DIFFERENTIATED_M1M2_W2` | `NA_NETAWARE_2T_4N_L1_DIFFERENTIATED_M1M2_W2` |
| `P1` | `2T_4N_L2_DIFFERENTIATED_M1M2_W2` | `NA_DEFAULT_2T_4N_L2_DIFFERENTIATED_M1M2_W2` | `NA_LOADAWARE_2T_4N_L2_DIFFERENTIATED_M1M2_W2` | `NA_NETAWARE_2T_4N_L2_DIFFERENTIATED_M1M2_W2` |
| `P1` | `3T_4N_L1_DIFFERENTIATED_M1M1M1_W2` | `NA_DEFAULT_3T_4N_L1_DIFFERENTIATED_M1M1M1_W2` | `NA_LOADAWARE_3T_4N_L1_DIFFERENTIATED_M1M1M1_W2` | `NA_NETAWARE_3T_4N_L1_DIFFERENTIATED_M1M1M1_W2` |
| `P1` | `3T_4N_L2_DIFFERENTIATED_M1M1M1_W2` | `NA_DEFAULT_3T_4N_L2_DIFFERENTIATED_M1M1M1_W2` | `NA_LOADAWARE_3T_4N_L2_DIFFERENTIATED_M1M1M1_W2` | `NA_NETAWARE_3T_4N_L2_DIFFERENTIATED_M1M1M1_W2` |
| `P0` | `2T_4N_L3_DIFFERENTIATED_M1M1_W2` | `NA_DEFAULT_2T_4N_L3_DIFFERENTIATED_M1M1_W2` | `NA_LOADAWARE_2T_4N_L3_DIFFERENTIATED_M1M1_W2` | `NA_NETAWARE_2T_4N_L3_DIFFERENTIATED_M1M1_W2` |
| `P1` | `2T_4N_L3_DIFFERENTIATED_M1M2_W2` | `NA_DEFAULT_2T_4N_L3_DIFFERENTIATED_M1M2_W2` | `NA_LOADAWARE_2T_4N_L3_DIFFERENTIATED_M1M2_W2` | `NA_NETAWARE_2T_4N_L3_DIFFERENTIATED_M1M2_W2` |

The default campaign replica set is:

```text
A,B,C
```

The `L3` scenarios use `L3_INTER_GROUP_EXTREME`, an annotation-controlled inter-group latency profile designed to make placement differences easier to interpret under a more severe network condition.

---

## Scheduler Modes

| Variant family | Scheduler mode | Scheduler name expected in runtime evidence | Required plugin evidence |
|---|---|---|---|
| `NA_DEFAULT_*` | `kubernetes_default_scheduler` | `default-scheduler` in generated benchmark metadata; `spec.schedulerName` absent in LocalAI manifests. | No custom scheduler plugin required. |
| `NA_LOADAWARE_*` | `loadaware_custom_scheduler` | `scheduler-plugins-scheduler` in generated benchmark metadata and LocalAI pod specs. | `LoadAwareResourcesBalancedAllocation`. |
| `NA_NETAWARE_*` | `localai_resource_network_aware_scheduler` | `scheduler-plugins-scheduler` in generated benchmark metadata and LocalAI pod specs. | `LoadAwareResourcesBalancedAllocation` and `NetworkAwareLocalAi`. |

The runtime benchmark configuration generated for each variant must include:

```text
schedulerMode
schedulerName
effectiveSchedulerName
benchmarkAccessMode
trafficProfile
latencyProfile
```

The network-aware runtime configuration must include:

```text
runtimeScenario
networkObservability
istioGateway
monAgent
rescheduling
clusterLens
reporting
completionGate
freeze
```

---

## Network-Aware Runtime Requirements

C9 depends on a complete telemetry chain. Before interpreting results, verify that the following requirements are met.

| Requirement | Expected evidence |
|---|---|
| Gateway-routed traffic | Istio Gateway and VirtualService route benchmark traffic to each tenant's LocalAI master service. |
| Tenant identity | LocalAI workloads expose `group`, `app`, and `role` labels. |
| Master-worker distinction | Master pods expose `role=master`; worker pods expose `role=worker`. |
| Gateway traffic key | The scheduler receives `GATEWAY_TRAFFIC_KEY=traffic.localai-gateway-istio` or the configured profile value. |
| Node telemetry | Worker nodes expose `network-latency.<node>`, `packet-loss.<node>`, and `network-bandwidth.<node>` annotations when required. |
| Deployment telemetry | Selected deployments expose CPU, memory, and gateway traffic or peer traffic annotations. |
| Inter-node telemetry | Mentat exports and validates latency, packet loss, and bandwidth evidence. |
| Telemetry-gated redeployment | Controlled redeployment occurs after telemetry priming and before the official measurement window when required by the scheduler mode and scenario profile. |
| Placement snapshot capture | cluster-lens capture runs at the configured stages and writes raw topology, Kubernetes snapshots, placement summary, placement signature CSV, and capture manifest artifacts. |

If these requirements are not met, C9 results may still be valuable as negative evidence, but they must not be interpreted as a complete network-aware comparison unless telemetry, placement, and scheduler evidence are all available.

---

## Step 1 - Verify Required Files

### Windows PowerShell

```powershell
$RequiredFiles = @(
  ".\config\experimental-cycles\C9.json",
  ".\config\scenarios\network-aware-scheduler\NETWORK_AWARE_SCHEDULER_SCENARIOS_INDEX.json",
  ".\config\scheduler\profiles\CS_C9_LOADAWARE_SECOND_SCHEDULER.json",
  ".\config\scheduler\profiles\CS_C9_LOCALAI_RESOURCE_NETWORK_AWARE_SECOND_SCHEDULER.json",
  ".\config\mon-agent\profiles\MA_NETWORK_AWARE.json",
  ".\config\network-observability\profiles\NO_MENTAT_C9.json",
  ".\config\istio-gateway\profiles\IG_LOCALAI_GATEWAY_ROUTED_C9.json",
  ".\config\cluster-lens\CLUSTER_LENS_INDEX.json",
  ".\config\cluster-lens\profiles\CL_C9_PLACEMENT_SNAPSHOT.json",
  ".\scripts\observability\cluster-lens\capture-cluster-lens-snapshot.py",
  ".\scripts\observability\cluster-lens\Capture-ClusterLensSnapshot.ps1",
  ".\scripts\observability\cluster-lens\capture-cluster-lens-snapshot.sh",
  ".\config\rescheduling\profiles\RS_C9_NETWORK_AWARE_TELEMETRY_PRIMED_REDEPLOYMENT.json",
  ".\config\infrastructure\profiles\INFRA_C9_1CP_4W_8C16G.json",
  ".\config\infrastructure\providers\proxmox-k3s\bindings\BINDING_INFRA_C9_1CP_4W_8C16G_PROXMOX_K3S.json",
  ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c9-1cp-4w-8c16g.local.yaml",
  ".\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1",
  ".\scripts\experimental-cycles\run-experimental-campaign.py",
  ".\scripts\validation\scheduler\validate-scheduler-mode-manifests.py",
  ".\scripts\istio\validate-istio-gateway.py",
  ".\scripts\network-observability\validate-mentat.py"
)

foreach ($Path in $RequiredFiles) {
  if (-not (Test-Path $Path)) {
    throw "Missing required C9 file: $Path"
  }
}
```

### Bash

```bash
required_files=(
  "./config/experimental-cycles/C9.json"
  "./config/scenarios/network-aware-scheduler/NETWORK_AWARE_SCHEDULER_SCENARIOS_INDEX.json"
  "./config/scheduler/profiles/CS_C9_LOADAWARE_SECOND_SCHEDULER.json"
  "./config/scheduler/profiles/CS_C9_LOCALAI_RESOURCE_NETWORK_AWARE_SECOND_SCHEDULER.json"
  "./config/mon-agent/profiles/MA_NETWORK_AWARE.json"
  "./config/network-observability/profiles/NO_MENTAT_C9.json"
  "./config/istio-gateway/profiles/IG_LOCALAI_GATEWAY_ROUTED_C9.json"
  "./config/cluster-lens/CLUSTER_LENS_INDEX.json"
  "./config/cluster-lens/profiles/CL_C9_PLACEMENT_SNAPSHOT.json"
  "./scripts/observability/cluster-lens/capture-cluster-lens-snapshot.py"
  "./scripts/observability/cluster-lens/Capture-ClusterLensSnapshot.ps1"
  "./scripts/observability/cluster-lens/capture-cluster-lens-snapshot.sh"
  "./config/rescheduling/profiles/RS_C9_NETWORK_AWARE_TELEMETRY_PRIMED_REDEPLOYMENT.json"
  "./config/infrastructure/profiles/INFRA_C9_1CP_4W_8C16G.json"
  "./config/infrastructure/providers/proxmox-k3s/bindings/BINDING_INFRA_C9_1CP_4W_8C16G_PROXMOX_K3S.json"
  "./config/infrastructure/providers/proxmox-k3s/local/cluster.c9-1cp-4w-8c16g.local.yaml"
  "./scripts/experimental-cycles/start-experimental-campaign.sh"
  "./scripts/experimental-cycles/run-experimental-campaign.py"
  "./scripts/validation/scheduler/validate-scheduler-mode-manifests.py"
  "./scripts/istio/validate-istio-gateway.py"
  "./scripts/network-observability/validate-mentat.py"
)

for path in "${required_files[@]}"; do
  test -f "$path" || { echo "Missing required C9 file: $path" >&2; exit 1; }
done
```

---

## Step 2 - Validate JSON Configuration Syntax

### Windows PowerShell

```powershell
python - <<'PY'
import json
from pathlib import Path
paths = [
    Path("config/experimental-cycles/C9.json"),
    Path("config/scenarios/network-aware-scheduler/NETWORK_AWARE_SCHEDULER_SCENARIOS_INDEX.json"),
    *Path("config/scenarios/network-aware-scheduler").glob("NA_*.json"),
    Path("config/scheduler/profiles/CS_C9_LOADAWARE_SECOND_SCHEDULER.json"),
    Path("config/scheduler/profiles/CS_C9_LOCALAI_RESOURCE_NETWORK_AWARE_SECOND_SCHEDULER.json"),
    Path("config/mon-agent/profiles/MA_NETWORK_AWARE.json"),
    Path("config/network-observability/profiles/NO_MENTAT_C9.json"),
    Path("config/istio-gateway/profiles/IG_LOCALAI_GATEWAY_ROUTED_C9.json"),
    Path("config/cluster-lens/CLUSTER_LENS_INDEX.json"),
    Path("config/cluster-lens/profiles/CL_C9_PLACEMENT_SNAPSHOT.json"),
    Path("config/cluster-lens/schemas/CLUSTER_LENS_PROFILE_SCHEMA_V1.json"),
    Path("config/rescheduling/profiles/RS_C9_NETWORK_AWARE_TELEMETRY_PRIMED_REDEPLOYMENT.json"),
    Path("config/technical-diagnosis/profiles/TD_C9_NETWORK_AWARE_SCHEDULER.json"),
    Path("config/reporting/profiles/RP_C9_NETWORK_AWARE_SCHEDULER.json"),
    Path("config/completion-gate/profiles/CG_C9_NETWORK_AWARE_SCHEDULER.json"),
    Path("config/freeze/profiles/FR_C9_NETWORK_AWARE_SCHEDULER.json"),
]
for path in paths:
    with path.open("r", encoding="utf-8") as handle:
        json.load(handle)
    print(f"OK {path}")
PY
```

### Bash

```bash
python3 - <<'PY'
import json
from pathlib import Path
paths = [
    Path("config/experimental-cycles/C9.json"),
    Path("config/scenarios/network-aware-scheduler/NETWORK_AWARE_SCHEDULER_SCENARIOS_INDEX.json"),
    *Path("config/scenarios/network-aware-scheduler").glob("NA_*.json"),
    Path("config/scheduler/profiles/CS_C9_LOADAWARE_SECOND_SCHEDULER.json"),
    Path("config/scheduler/profiles/CS_C9_LOCALAI_RESOURCE_NETWORK_AWARE_SECOND_SCHEDULER.json"),
    Path("config/mon-agent/profiles/MA_NETWORK_AWARE.json"),
    Path("config/network-observability/profiles/NO_MENTAT_C9.json"),
    Path("config/istio-gateway/profiles/IG_LOCALAI_GATEWAY_ROUTED_C9.json"),
    Path("config/cluster-lens/CLUSTER_LENS_INDEX.json"),
    Path("config/cluster-lens/profiles/CL_C9_PLACEMENT_SNAPSHOT.json"),
    Path("config/cluster-lens/schemas/CLUSTER_LENS_PROFILE_SCHEMA_V1.json"),
    Path("config/rescheduling/profiles/RS_C9_NETWORK_AWARE_TELEMETRY_PRIMED_REDEPLOYMENT.json"),
    Path("config/technical-diagnosis/profiles/TD_C9_NETWORK_AWARE_SCHEDULER.json"),
    Path("config/reporting/profiles/RP_C9_NETWORK_AWARE_SCHEDULER.json"),
    Path("config/completion-gate/profiles/CG_C9_NETWORK_AWARE_SCHEDULER.json"),
    Path("config/freeze/profiles/FR_C9_NETWORK_AWARE_SCHEDULER.json"),
]
for path in paths:
    with path.open("r", encoding="utf-8") as handle:
        json.load(handle)
    print(f"OK {path}")
PY
```

---

## Step 3 - Validate Network-Aware Scheduler Manifests

C9 uses network-aware scheduler compositions. They must preserve scheduler-mode semantics, LocalAI tenant labels, and the gateway-routed access model.

### Windows PowerShell

```powershell
New-Item -ItemType Directory -Force -Path .\results\validation | Out-Null
python .\scripts\validation\scheduler\validate-scheduler-mode-manifests.py `
  --repo-root . `
  --scan-root .\infra\k8s\compositions\network-aware-scheduler `
  --require-render `
  --json | Out-File .\results\validation\network-aware-scheduler-c9-manifest-validation.json -Encoding utf8
```

### Bash

```bash
mkdir -p results/validation
python3 scripts/validation/scheduler/validate-scheduler-mode-manifests.py \
  --repo-root . \
  --scan-root infra/k8s/compositions/network-aware-scheduler \
  --require-render \
  --json > results/validation/network-aware-scheduler-c9-manifest-validation.json
```

The validation result should confirm that C9 manifests expose the labels needed by the scheduler:

```text
group
app
role
```

and that default-scheduler variants do not set `spec.schedulerName`.

---

## Step 4 - Inspect the Scenario Triplet Model

Validate that every logical scenario has exactly one default variant, one load-aware variant, and one network-aware variant.

### Windows PowerShell

```powershell
python - <<'PY'
import json
from collections import defaultdict
from pathlib import Path
index = json.loads(Path("config/scenarios/network-aware-scheduler/NETWORK_AWARE_SCHEDULER_SCENARIOS_INDEX.json").read_text(encoding="utf-8"))
logical = defaultdict(list)
for item in index.get("scenarios", []):
    path = Path(item.get("path") or item.get("scenarioConfigPath", ""))
    payload = json.loads(path.read_text(encoding="utf-8"))
    logical[payload.get("logicalScenarioId")].append((payload.get("schedulerMode"), payload.get("variantId")))
expected = ["kubernetes_default_scheduler", "loadaware_custom_scheduler", "localai_resource_network_aware_scheduler"]
for key, values in sorted(logical.items()):
    print(key, values)
    modes = sorted(mode for mode, _ in values)
    if modes != sorted(expected):
        raise SystemExit(f"Invalid scheduler triplet for {key}: {modes}")
PY
```

### Bash

```bash
python3 - <<'PY'
import json
from collections import defaultdict
from pathlib import Path
index = json.loads(Path("config/scenarios/network-aware-scheduler/NETWORK_AWARE_SCHEDULER_SCENARIOS_INDEX.json").read_text(encoding="utf-8"))
logical = defaultdict(list)
for item in index.get("scenarios", []):
    path = Path(item.get("path") or item.get("scenarioConfigPath", ""))
    payload = json.loads(path.read_text(encoding="utf-8"))
    logical[payload.get("logicalScenarioId")].append((payload.get("schedulerMode"), payload.get("variantId")))
expected = ["kubernetes_default_scheduler", "loadaware_custom_scheduler", "localai_resource_network_aware_scheduler"]
for key, values in sorted(logical.items()):
    print(key, values)
    modes = sorted(mode for mode, _ in values)
    if modes != sorted(expected):
        raise SystemExit(f"Invalid scheduler triplet for {key}: {modes}")
PY
```

---

## Step 5 - Produce a Dry-Run Campaign Plan

A dry run verifies campaign expansion, generated runtime configuration paths, provider binding resolution, scheduler-mode expansion, and runtime command construction without creating infrastructure.

### Windows PowerShell

```powershell
$CycleConfig = ".\config\experimental-cycles\C9.json"
$RunId = "C9_network_aware_scheduler_dry_run"

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig $CycleConfig `
  -RunId $RunId `
  -BaselineReplicas "A,B,C" `
  -DryRun `
  -SkipDelete
```

### Bash

```bash
CYCLE_CONFIG="./config/experimental-cycles/C9.json"
RUN_ID="C9_network_aware_scheduler_dry_run"

./scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config "$CYCLE_CONFIG" \
  --run-id "$RUN_ID" \
  --baseline-replicas "A,B,C" \
  --dry-run \
  --skip-delete
```

After the dry run, inspect:

```text
results/experimental-cycles/C9/execution/
results/experimental-cycles/C9/execution/generated-runtime-configs/
```

Generated runtime configs must contain `runtimeScenario`, `networkObservability`, `istioGateway`, `monAgent`, `rescheduling`, `reporting`, `completionGate`, and `freeze`.

---

## Step 6 - Execute the Complete C9 Campaign

Use this command only when the local provider YAML has been reviewed, cluster deletion is expected by the lifecycle policy, and the environment is ready for a full campaign.

### Windows PowerShell

```powershell
$CycleConfig = ".\config\experimental-cycles\C9.json"
$RunId = "C9_network_aware_scheduler"

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig $CycleConfig `
  -RunId $RunId `
  -BaselineReplicas "A,B,C" `
  -ConfirmDelete `
  -ForceFreeze `
  -WriteLatestAliases
```

### Bash

```bash
CYCLE_CONFIG="./config/experimental-cycles/C9.json"
RUN_ID="C9_network_aware_scheduler"

./scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config "$CYCLE_CONFIG" \
  --run-id "$RUN_ID" \
  --baseline-replicas "A,B,C" \
  --confirm-delete \
  --force-freeze \
  --write-latest-aliases
```

Do not use `--skip-completion-gate` or `--skip-freeze` for the final campaign unless the run is explicitly partial or diagnostic.

---

## Step 7 - Inspect Campaign Execution Outputs

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C9\execution -Recurse | Select-Object FullName
Get-ChildItem .\results\experimental-cycles\C9\execution\generated-runtime-configs
```

### Bash

```bash
find ./results/experimental-cycles/C9/execution -maxdepth 4 -type f | sort
find ./results/experimental-cycles/C9/execution/generated-runtime-configs -maxdepth 2 -type f | sort
```

Each variant should have a generated runtime config under:

```text
results/experimental-cycles/C9/execution/generated-runtime-configs/<variant-id>/<variant-id>.cycle.json
```

---

## Step 8 - Inspect Istio Gateway Evidence

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C9\variants -Recurse -Directory |
  Where-Object { $_.FullName -like "*network-aware-scheduler*istio*" } |
  Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C9/variants -path "*/network-aware-scheduler/istio/*" -type f | sort
```

The Istio evidence must show that benchmark traffic is routed through the configured gateway path instead of direct service port-forwarding.

Expected access mode:

```text
istio_gateway_routed
```

---

## Step 9 - Inspect mon-agent and Deployment Annotation Evidence

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C9\variants -Recurse -Directory |
  Where-Object { $_.FullName -like "*network-aware-scheduler*mon-agent*" } |
  Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C9/variants -path "*/network-aware-scheduler/mon-agent/*" -type f | sort
```

The mon-agent validation evidence must confirm the required runtime annotations, including:

```text
cpu-usage
memory-usage
network-latency.<node>
packet-loss.<node>
network-bandwidth.<node>
traffic.localai-gateway-istio
```

Deployment traffic annotations may also appear through peer-workload forms such as:

```text
traffic.<peer-workload>
rps.<peer-workload>
```

---

## Step 10 - Inspect Mentat Network Observability Evidence

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C9\variants -Recurse -Directory |
  Where-Object { $_.FullName -like "*network-aware-scheduler*mentat*" } |
  Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C9/variants -path "*/network-aware-scheduler/mentat/*" -type f | sort
```

Mentat evidence must preserve inter-node telemetry for:

```text
node_latency
node_packet_loss_ratio
node_bandwidth_bytes_per_second
node_bandwidth_probe_failures_total
```

The expected metric labels are:

```text
origin_node
destination_node
```

---

## Step 11 - Inspect Custom Scheduler Evidence

Load-aware and network-aware variants must install and validate the custom second scheduler.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C9\scheduler\custom-scheduler -Recurse |
  Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C9/scheduler/custom-scheduler -maxdepth 5 -type f | sort
```

The network-aware custom scheduler evidence must confirm:

```text
scheduler-plugins-scheduler
LoadAwareResourcesBalancedAllocation
NetworkAwareLocalAi
GATEWAY_TRAFFIC_KEY
```

For NETAWARE variants, the configured gateway traffic key must match the scheduler profile and the mon-agent annotation evidence.

---

## Step 12 - Inspect Telemetry-Primed Rescheduling Evidence

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C9\variants -Recurse -Directory |
  Where-Object { $_.FullName -like "*network-aware-scheduler*rescheduling*" } |
  Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C9/variants -path "*/network-aware-scheduler/rescheduling/*" -type f | sort
```

Rescheduling evidence must preserve:

1. pre-redeployment placement and annotation snapshots;
2. telemetry priming status;
3. gateway traffic key evidence;
4. annotation gate status;
5. latency matrix validation status for `L1`, `L2`, and `L3` scenarios;
6. controlled annotation-window attempts when an annotation-controlled latency matrix is in use;
7. controlled pod recreation status;
8. post-redeployment placement and annotation snapshots;
9. readiness status before the official measurement window.

For latency-differentiated C9 scenarios that rely on annotation-controlled latency values, the rescheduling profile should converge the scheduler-facing `network-latency.<node>` matrix immediately before pod recreation. This protects the measurement window from ambiguous input when periodic telemetry updates and controlled latency annotations target the same node annotation keys.

---

## Step 13 - Inspect Scheduler Decision Evidence

Scheduler decision evidence must exist for default, load-aware, and network-aware variants.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C9 -Recurse -Filter network-aware-scheduler-decision-evidence.json |
  Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C9 -name network-aware-scheduler-decision-evidence.json -type f | sort
```

For NETAWARE variants, confirm that scheduled pods were associated with:

```text
scheduler-plugins-scheduler
```

and that scheduler evidence preserves the `group`, `app`, and `role` labels used to distinguish tenant, workload identity, and LocalAI master/worker role.

---

## Step 14 - Inspect cluster-lens Placement Evidence

cluster-lens placement evidence must be available for each executed C9 variant unless the capture was explicitly skipped. The primary placement evidence is saved under the variant-level `cluster-lens/` root. Additional stage-specific snapshots are saved under `cluster-lens/stages/`.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C9\variants -Recurse -Filter cluster-lens-placement-summary.json |
  Select-Object FullName

Get-ChildItem .\results\experimental-cycles\C9\variants -Recurse -Filter cluster-lens-placement-signature.csv |
  Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C9/variants -name cluster-lens-placement-summary.json -type f | sort
find ./results/experimental-cycles/C9/variants -name cluster-lens-placement-signature.csv -type f | sort
```

The placement signature should be used to compare tenant, master, worker, deployment, schedulerName, and node assignment across the `DEFAULT`, `LOADAWARE`, and `NETAWARE` variants for the same logical scenario.

Interpret cluster-lens evidence at two levels:

1. **Cluster topology stability**: Kubernetes node count, cluster-lens node count, node edges, and application edges should normally remain stable across the three scheduler modes for the same logical scenario. A stable topology means that the infrastructure context is comparable.
2. **Pod-placement variation**: tenant master nodes, tenant worker nodes, distinct tenant nodes, co-location fields, unscheduled pods, and scheduler names are the fields that show whether the scheduler changed LocalAI pod placement.

For C9 report review, use the generated cycle report sections named `Network-aware latency profile context`, `Cluster-lens placement evidence summary`, and `Cluster-lens tenant placement`. The first section establishes the latency context, the second verifies the selected primary placement evidence, and the third exposes the tenant-level pod-to-node assignments used for scheduler comparison.

The primary cluster-lens evidence should be read from the variant-level `cluster-lens/` root. Stage-specific captures under `cluster-lens/stages/<capture-stage>/` remain useful for audit and troubleshooting. If a report row indicates that a fallback stage was used, inspect the corresponding primary-stage manifest and verify that the fallback is methodologically acceptable for the affected scheduler mode.

---

## Step 15 - Inspect Benchmark Outputs

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C9\benchmark\network-aware-scheduler -Recurse |
  Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C9/benchmark/network-aware-scheduler -maxdepth 5 -type f | sort
```

For each variant and replica, inspect Locust CSV files, protocol artifacts, metric-set artifacts, scenario status files, and tenant-specific benchmark metadata.

Benchmark artifacts must preserve scheduler-aware and gateway-aware metadata and must not label NETAWARE variants as default-scheduler executions.

---

## Step 16 - Inspect Diagnosis, Reporting, Completion Gate, and Freeze

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C9\diagnosis -Recurse | Select-Object FullName
Get-ChildItem .\results\experimental-cycles\C9\reporting -Recurse | Select-Object FullName
Get-ChildItem .\results\experimental-cycles\C9\completion-gate -Recurse | Select-Object FullName
Get-ChildItem .\results\experimental-cycles\C9\freeze -Recurse | Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C9/diagnosis -maxdepth 5 -type f | sort
find ./results/experimental-cycles/C9/reporting -maxdepth 5 -type f | sort
find ./results/experimental-cycles/C9/completion-gate -maxdepth 5 -type f | sort
find ./results/experimental-cycles/C9/freeze -maxdepth 5 -type f | sort
```

The C9 completion gate should evaluate the campaign as a three-way scheduler evaluation. A final complete execution should provide enough evidence for scenario coverage, scheduler-mode comparison, gateway-routed traffic, mon-agent annotation evidence, Mentat evidence, telemetry-primed rescheduling, scheduler decision capture, cluster-lens placement evidence, benchmark outputs, diagnosis, reporting, and freeze.

---

## Optional - Direct Variant Execution

The preferred execution surface is the campaign runner. Direct execution of a generated runtime config is useful only for diagnosis or targeted reruns.

### Windows PowerShell

```powershell
$VariantConfig = ".\results\experimental-cycles\C9\execution\generated-runtime-configs\NA_NETAWARE_2T_4N_L2_DIFFERENTIATED_M1M1_W2\NA_NETAWARE_2T_4N_L2_DIFFERENTIATED_M1M1_W2.cycle.json"

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\experimental-cycles\Start-ExperimentalCycle.ps1 `
  -CycleConfig $VariantConfig `
  -ExecutionScope provider-backed-cycle `
  -RunId "C9_direct_variant_diagnostic" `
  -ConfirmDelete `
  -ForceFreeze `
  -WriteLatestAliases
```

### Bash

```bash
VARIANT_CONFIG="./results/experimental-cycles/C9/execution/generated-runtime-configs/NA_NETAWARE_2T_4N_L2_DIFFERENTIATED_M1M1_W2/NA_NETAWARE_2T_4N_L2_DIFFERENTIATED_M1M1_W2.cycle.json"

./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$VARIANT_CONFIG" \
  --execution-scope provider-backed-cycle \
  --run-id "C9_direct_variant_diagnostic" \
  --confirm-delete \
  --force-freeze \
  --write-latest-aliases
```

Do not treat a single direct variant run as a complete C9 campaign result.

---

## Interpretation Checklist

Use the following checklist when reading C9 outputs:

- Does each logical scenario have default, load-aware, and network-aware variants?
- Are infrastructure, tenant count, worker count, model mix, traffic profile, access mode, and latency profile constant within each scheduler-mode triplet?
- Does the default variant omit `spec.schedulerName`?
- Does the load-aware variant use `scheduler-plugins-scheduler` with `LoadAwareResourcesBalancedAllocation`?
- Does the network-aware variant use `scheduler-plugins-scheduler` with both `LoadAwareResourcesBalancedAllocation` and `NetworkAwareLocalAi`?
- Did the benchmark traffic use Istio gateway routing?
- Did `mon-agent` produce required node and deployment annotations before controlled redeployment?
- Did Mentat provide inter-node latency, packet-loss, and bandwidth evidence?
- Did controlled redeployment occur after telemetry priming and before the official measurement window?
- Did scheduler decision evidence capture pod-to-node placement after redeployment?
- Are unsupported or inconclusive scenarios explained by infrastructure, scheduling, rollout, annotation, network telemetry, gateway routing, or workload constraints?
- Does reporting compare DEFAULT, LOADAWARE, and NETAWARE variants by logical scenario?
- Does the freeze snapshot preserve all relevant evidence?

---

## Readiness Checklist

C9 is ready for final execution when:

- `proxmox-k3s` is available;
- Helm is available for custom scheduler installation;
- C9 local provider YAML is reviewed and ignored by Git;
- the provider YAML enables monitoring, `mon-agent`, cluster-lens, Mentat, and Istio add-ons;
- C9 cluster validation checks the management node and four worker-node expectations;
- network-aware scheduler manifests pass static validation;
- `mon-agent`, Mentat, Istio, scheduler, rescheduling, diagnosis, reporting, completion-gate, and freeze profiles are present;
- C9 dry-run campaign produces all forty-two generated runtime configs;
- destructive deletion is intentional and `-ConfirmDelete` or `--confirm-delete` is supplied;
- the operator is ready to regenerate all C9 result artifacts from current source configuration.

---

## Next Runbook

Continue with:

```text
docs/runbooks/12-localai-deployment-topologies-and-placement.md
```
