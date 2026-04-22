#!/usr/bin/env bash
set -euo pipefail

FAMILY="all"
PROFILE_CONFIG=""
BASE_URL="http://localhost:8080"
OUTPUT_ROOT=""
KUBECONFIG_PATH=""
NAMESPACE_OVERRIDE=""
SKIP_PRECHECK=false
SKIP_API_SMOKE=false
CONTINUE_ON_FAILURE=false
STATISTICAL_RIGOR_CONFIG=""
DRY_RUN=false

print_usage() {
  cat <<'USAGE'
Usage:
  ./start-consolidated-pilot-benchmarks.sh [options]

Options:
  --family worker-count|workload|models|placement|all | -Family VALUE
  --profile-config PATH | -ProfileConfig PATH
  --base-url URL | -BaseUrl URL
  --output-root PATH | -OutputRoot PATH
  --kubeconfig PATH | -Kubeconfig PATH
  --namespace NAME | -Namespace NAME
  --skip-precheck | -SkipPrecheck
  --skip-api-smoke | -SkipApiSmoke
  --continue-on-failure | -ContinueOnFailure
  --statistical-rigor-config PATH | -StatisticalRigorConfig PATH
  --dry-run | -DryRun
  --help | -Help
USAGE
}

require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Errore: il comando richiesto non è disponibile nel PATH: $cmd" >&2
    exit 1
  fi
}

resolve_repo_root() {
  local script_dir
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  cd -- "$script_dir/../../.." && pwd
}

validate_family() {
  case "$1" in
    worker-count|workload|models|placement|all) ;;
    *)
      echo "Famiglia non supportata: $1" >&2
      exit 1
      ;;
  esac
}

append_entry() {
  local entries_file="$1"
  local entry_json="$2"
  printf '%s\n' "$entry_json" >> "$entries_file"
}

get_kubectl_json_for_consolidation() {
  local kubeconfig_path="$1"
  shift

  local cmd=(kubectl)
  if [[ -n "$kubeconfig_path" ]]; then
    cmd+=(--kubeconfig "$kubeconfig_path")
  fi
  cmd+=("$@" -o json)

  "${cmd[@]}"
}

wait_consolidated_cluster_stabilization() {
  local namespace="$1"
  local kubeconfig_path="$2"
  local timeout_seconds="$3"
  local poll_interval_seconds="$4"

  local deadline=$(( $(date +%s) + timeout_seconds ))
  local last_reason="Cluster stabilization check not yet executed."
  local python_cmd
  python_cmd="$(pilot_consolidation_require_python_command)"

  while (( $(date +%s) < deadline )); do
    local deployments_json_file
    local pods_json_file
    deployments_json_file="$(mktemp)"
    pods_json_file="$(mktemp)"

    if ! get_kubectl_json_for_consolidation "$kubeconfig_path" get deployments -n "$namespace" > "$deployments_json_file"; then
      rm -f -- "$deployments_json_file" "$pods_json_file"
      echo "Errore durante il recupero dei deployment per la stabilizzazione del cluster." >&2
      return 1
    fi

    if ! get_kubectl_json_for_consolidation "$kubeconfig_path" get pods -n "$namespace" > "$pods_json_file"; then
      rm -f -- "$deployments_json_file" "$pods_json_file"
      echo "Errore durante il recupero dei pod per la stabilizzazione del cluster." >&2
      return 1
    fi

    local analysis
    analysis="$($python_cmd - "$deployments_json_file" "$pods_json_file" <<'PY2'
import json
import sys
from pathlib import Path

def parse_json(path_str):
    return json.loads(Path(path_str).read_text(encoding='utf-8-sig'))

deployments_json = parse_json(sys.argv[1])
pods_json = parse_json(sys.argv[2])

deployments = []
for item in deployments_json.get('items', []):
    name = str(item.get('metadata', {}).get('name', ''))
    if name == 'localai-server' or name.startswith('localai-rpc-'):
        deployments.append(item)

pods = []
for item in pods_json.get('items', []):
    name = str(item.get('metadata', {}).get('name', ''))
    if name.startswith('localai-server') or name.startswith('localai-rpc-'):
        pods.append(item)

if not deployments:
    print('WAIT	0	0	Nessun deployment LocalAI osservato nel namespace specificato.')
    raise SystemExit(0)

if not pods:
    print('WAIT	{}	0	Nessun pod LocalAI osservato nel namespace specificato.'.format(len(deployments)))
    raise SystemExit(0)

deployment_issues = []
for deployment in deployments:
    metadata = deployment.get('metadata', {})
    spec = deployment.get('spec', {})
    status = deployment.get('status', {})
    name = str(metadata.get('name', ''))
    spec_replicas = int(spec.get('replicas', 1) if spec.get('replicas', 1) is not None else 1)
    ready_replicas = int(status.get('readyReplicas', 0) or 0)
    updated_replicas = int(status.get('updatedReplicas', 0) or 0)
    available_replicas = int(status.get('availableReplicas', 0) or 0)
    observed_generation = int(status.get('observedGeneration', 0) or 0)
    generation = int(metadata.get('generation', 0) or 0)

    if observed_generation < generation:
        deployment_issues.append(f'{name}: observedGeneration={observed_generation} < generation={generation}')
        continue

    if ready_replicas < spec_replicas or updated_replicas < spec_replicas or available_replicas < spec_replicas:
        deployment_issues.append(
            f'{name}: replicas spec={spec_replicas}, ready={ready_replicas}, updated={updated_replicas}, available={available_replicas}'
        )

pod_issues = []
for pod in pods:
    metadata = pod.get('metadata', {})
    status = pod.get('status', {})
    name = str(metadata.get('name', ''))

    if metadata.get('deletionTimestamp') is not None:
        pod_issues.append(f'{name}: in terminazione')
        continue

    phase = str(status.get('phase', ''))
    if phase != 'Running':
        pod_issues.append(f'{name}: phase={phase}')
        continue

    conditions = status.get('conditions') or []
    ready_condition = next((condition for condition in conditions if condition.get('type') == 'Ready'), None)
    if ready_condition is None or str(ready_condition.get('status', '')) != 'True':
        pod_issues.append(f'{name}: Ready condition non soddisfatta')

if not deployment_issues and not pod_issues:
    print(f'OK	{len(deployments)}	{len(pods)}	Deployment e pod LocalAI risultano stabili nel namespace specificato.')
    raise SystemExit(0)

issue_parts = []
if deployment_issues:
    issue_parts.append('deployment non stabili: ' + '; '.join(deployment_issues))
if pod_issues:
    issue_parts.append('pod non stabili: ' + '; '.join(pod_issues))
print(f'WAIT	{len(deployments)}	{len(pods)}	' + ' | '.join(issue_parts))
PY2
)"

    rm -f -- "$deployments_json_file" "$pods_json_file"

    local state deployment_count pod_count summary
    IFS=$'\t' read -r state deployment_count pod_count summary <<< "$analysis"

    if [[ "$state" == "OK" ]]; then
      printf '%s\t%s\t%s\n' "$deployment_count" "$pod_count" "$summary"
      return 0
    fi

    last_reason="$summary"
    sleep "$poll_interval_seconds"
  done

  echo "Timeout durante la stabilizzazione del cluster nel namespace '$namespace'. Ultima osservazione: $last_reason" >&2
  return 1
}


while [[ $# -gt 0 ]]; do
  case "$1" in
    --family|-Family)
      FAMILY="$2"
      shift 2
      ;;
    --profile-config|-ProfileConfig)
      PROFILE_CONFIG="$2"
      shift 2
      ;;
    --base-url|-BaseUrl)
      BASE_URL="$2"
      shift 2
      ;;
    --output-root|-OutputRoot)
      OUTPUT_ROOT="$2"
      shift 2
      ;;
    --kubeconfig|-Kubeconfig)
      KUBECONFIG_PATH="$2"
      shift 2
      ;;
    --namespace|-Namespace)
      NAMESPACE_OVERRIDE="$2"
      shift 2
      ;;
    --skip-precheck|-SkipPrecheck)
      SKIP_PRECHECK=true
      shift
      ;;
    --skip-api-smoke|-SkipApiSmoke)
      SKIP_API_SMOKE=true
      shift
      ;;
    --continue-on-failure|-ContinueOnFailure)
      CONTINUE_ON_FAILURE=true
      shift
      ;;
    --statistical-rigor-config|-StatisticalRigorConfig)
      STATISTICAL_RIGOR_CONFIG="$2"
      shift 2
      ;;
    --dry-run|-DryRun)
      DRY_RUN=true
      shift
      ;;
    --help|-Help)
      print_usage
      exit 0
      ;;
    *)
      echo "Argomento non riconosciuto: $1" >&2
      print_usage >&2
      exit 1
      ;;
  esac
done

validate_family "$FAMILY"
REPO_ROOT="$(resolve_repo_root)"
source "$REPO_ROOT/scripts/load/lib/bash/run-convention.sh"
source "$REPO_ROOT/scripts/load/lib/bash/run-pilot-consolidation.sh"
source "$REPO_ROOT/scripts/load/lib/bash/run-statistical-rigor.sh"

if [[ -z "$PROFILE_CONFIG" ]]; then
  PROFILE_CONFIG="$REPO_ROOT/config/pilot-consolidation/CP1.json"
fi

pilot_consolidation_load_profile "$PROFILE_CONFIG"

if [[ -z "$OUTPUT_ROOT" ]]; then
  OUTPUT_ROOT="$REPO_ROOT/$PILOT_CONSOLIDATION_OUTPUT_ROOT_REL"
fi

if [[ -z "$STATISTICAL_RIGOR_CONFIG" ]]; then
  STATISTICAL_RIGOR_CONFIG="$REPO_ROOT/$PILOT_CONSOLIDATION_STATISTICAL_RIGOR_CONFIG_REL"
fi

if [[ ! -f "$STATISTICAL_RIGOR_CONFIG" ]]; then
  echo "Il file di statistical rigor non esiste: $STATISTICAL_RIGOR_CONFIG" >&2
  exit 1
fi

statistical_rigor_load_profile "$STATISTICAL_RIGOR_CONFIG"
mkdir -p -- "$OUTPUT_ROOT/campaigns"

RUN_TIMESTAMP_UTC="$(rc_build_timestamp_utc)"
CAMPAIGN_SCOPE="$FAMILY"
CAMPAIGN_ID="$(rc_build_run_id "pilot" "consolidated" "$CAMPAIGN_SCOPE" "NA" "$RUN_TIMESTAMP_UTC")"
CAMPAIGN_MANIFEST_PATH="$OUTPUT_ROOT/campaigns/${CAMPAIGN_ID}${PILOT_CONSOLIDATION_MANIFEST_SUFFIX}"
CAMPAIGN_TEXT_PATH="$OUTPUT_ROOT/campaigns/${CAMPAIGN_ID}${PILOT_CONSOLIDATION_TEXT_SUFFIX}"
RIGOR_MANIFEST_PATH="$OUTPUT_ROOT/campaigns/${CAMPAIGN_ID}${STATISTICAL_RIGOR_SUMMARY_MANIFEST_SUFFIX}"
RIGOR_TEXT_PATH="$OUTPUT_ROOT/campaigns/${CAMPAIGN_ID}${STATISTICAL_RIGOR_SUMMARY_TEXT_SUFFIX}"
ENTRIES_FILE="$(mktemp)"
trap 'rm -f "$ENTRIES_FILE"' EXIT

if [[ "$FAMILY" == "all" ]]; then
  TARGET_FAMILIES=(worker-count workload models placement)
else
  TARGET_FAMILIES=("$FAMILY")
fi

REPORT_LINES=()
REPORT_LINES+=("=============================================")
REPORT_LINES+=(" Consolidated Pilot Benchmarks Launcher")
REPORT_LINES+=("=============================================")
REPORT_LINES+=("Repository              : $REPO_ROOT")
REPORT_LINES+=("Profile                 : $PILOT_CONSOLIDATION_PROFILE_FILE_RESOLVED")
REPORT_LINES+=("Profile ID              : $PILOT_CONSOLIDATION_PROFILE_ID")
REPORT_LINES+=("Campaign ID             : $CAMPAIGN_ID")
REPORT_LINES+=("Family scope            : $CAMPAIGN_SCOPE")
REPORT_LINES+=("Base URL                : $BASE_URL")
REPORT_LINES+=("Output root             : $OUTPUT_ROOT")
REPORT_LINES+=("Statistical rigor       : $STATISTICAL_RIGOR_PROFILE_FILE_RESOLVED")
REPORT_LINES+=("Replica cooldown (s)    : $STATISTICAL_RIGOR_COOLDOWN_BETWEEN_REPLICAS_SECONDS")
REPORT_LINES+=("Scenario cooldown (s)   : $STATISTICAL_RIGOR_COOLDOWN_BETWEEN_SCENARIOS_SECONDS")
REPORT_LINES+=("Stabilization timeout   : $STATISTICAL_RIGOR_STABILIZATION_TIMEOUT_SECONDS")
REPORT_LINES+=("Stabilization poll (s)  : $STATISTICAL_RIGOR_STABILIZATION_POLL_INTERVAL_SECONDS")
REPORT_LINES+=("Dry run                 : $DRY_RUN")
REPORT_LINES+=("Continue on failure     : $CONTINUE_ON_FAILURE")
REPORT_LINES+=("")

OVERALL_STATUS="success"
STOP_CAMPAIGN=false

for family_name in "${TARGET_FAMILIES[@]}"; do
  pilot_consolidation_load_family "$PROFILE_CONFIG" "$family_name"

  family_launcher="$REPO_ROOT/$PILOT_CONSOLIDATION_FAMILY_LAUNCHER_BASH_REL"
  family_output_root="$REPO_ROOT/$PILOT_CONSOLIDATION_FAMILY_OUTPUT_ROOT_REL"

  if [[ -n "$OUTPUT_ROOT" ]]; then
    family_output_root="$OUTPUT_ROOT/$family_name"
  fi

  if [[ ! -f "$family_launcher" ]]; then
    echo "Launcher di famiglia non trovato: $family_launcher" >&2
    exit 1
  fi

  mkdir -p -- "$family_output_root"

  mapfile -t FAMILY_SCENARIOS < <(pilot_consolidation_json_array_to_lines "$PILOT_CONSOLIDATION_FAMILY_SCENARIOS_JSON")
  mapfile -t FAMILY_REPLICAS < <(pilot_consolidation_json_array_to_lines "$PILOT_CONSOLIDATION_FAMILY_REPLICAS_JSON")

  REPORT_LINES+=("Family                : $family_name")
  REPORT_LINES+=("Launcher              : $family_launcher")
  REPORT_LINES+=("Output root           : $family_output_root")
  REPORT_LINES+=("Scenarios             : ${FAMILY_SCENARIOS[*]}")
  REPORT_LINES+=("Replicas              : ${FAMILY_REPLICAS[*]}")
  REPORT_LINES+=("")

  for ((scenario_index=0; scenario_index<${#FAMILY_SCENARIOS[@]}; scenario_index++)); do
    scenario="${FAMILY_SCENARIOS[$scenario_index]}"

    for ((replica_index=0; replica_index<${#FAMILY_REPLICAS[@]}; replica_index++)); do
      replica="${FAMILY_REPLICAS[$replica_index]}"
      CMD=(
        "$family_launcher"
        --scenario "$scenario"
        --replica "$replica"
        --base-url "$BASE_URL"
        --output-root "$family_output_root"
        --precheck-config "$REPO_ROOT/$PILOT_CONSOLIDATION_PRECHECK_CONFIG_REL"
        --phase-config "$REPO_ROOT/$PILOT_CONSOLIDATION_PHASE_CONFIG_REL"
        --warm-up-duration "$PILOT_CONSOLIDATION_WARM_UP_DURATION"
        --measurement-duration "$PILOT_CONSOLIDATION_MEASUREMENT_DURATION"
        --protocol-config "$REPO_ROOT/$PILOT_CONSOLIDATION_PROTOCOL_CONFIG_REL"
        --cluster-capture-config "$REPO_ROOT/$PILOT_CONSOLIDATION_CLUSTER_CAPTURE_CONFIG_REL"
        --metric-set-config "$REPO_ROOT/$PILOT_CONSOLIDATION_METRIC_SET_CONFIG_REL"
      )

      if [[ -n "$KUBECONFIG_PATH" ]]; then
        CMD+=(--kubeconfig "$KUBECONFIG_PATH")
      fi

      if [[ -n "$NAMESPACE_OVERRIDE" ]]; then
        CMD+=(--namespace "$NAMESPACE_OVERRIDE")
      fi

      if [[ "$SKIP_PRECHECK" == true ]]; then
        CMD+=(--skip-precheck)
      fi

      if [[ "$SKIP_API_SMOKE" == true ]]; then
        CMD+=(--skip-api-smoke)
      fi

      CMD+=(--auto-apply-k8s)

      if [[ "$DRY_RUN" == true ]]; then
        CMD+=(--dry-run)
      fi

      command_text=""
      for arg in "${CMD[@]}"; do
        command_text+=" $(printf '%q' "$arg")"
      done
      command_text="${command_text# }"
      REPORT_LINES+=("Run command           : $command_text")

      stats_csv_path=""

      if [[ "$DRY_RUN" == true ]]; then
        entry_json="$(statistical_rigor_build_entry_json "$family_name" "$scenario" "$replica" "dry_run" 0 "$command_text" "$stats_csv_path")"
        append_entry "$ENTRIES_FILE" "$entry_json"
      else
        run_started_epoch="$(date +%s)"
        set +e
        "${CMD[@]}"
        exit_code=$?
        set -e

        stats_csv_path="$(statistical_rigor_find_measurement_stats "$family_output_root" "$scenario" "$replica" "$run_started_epoch")"

        if [[ $exit_code -eq 0 ]]; then
          entry_json="$(statistical_rigor_build_entry_json "$family_name" "$scenario" "$replica" "success" "$exit_code" "$command_text" "$stats_csv_path")"
          append_entry "$ENTRIES_FILE" "$entry_json"
        elif [[ $exit_code -eq 42 ]]; then
          if [[ "$OVERALL_STATUS" == "success" ]]; then
            OVERALL_STATUS="completed_with_unsupported_scenarios"
          fi
          entry_json="$(statistical_rigor_build_entry_json "$family_name" "$scenario" "$replica" "unsupported_under_current_constraints" "$exit_code" "$command_text" "$stats_csv_path")"
          append_entry "$ENTRIES_FILE" "$entry_json"
          REPORT_LINES+=("Unsupported scenario  : family=$family_name scenario=$scenario replica=$replica exitCode=$exit_code (recorded as unsupported_under_current_constraints)")
        else
          OVERALL_STATUS="failed"
          entry_json="$(statistical_rigor_build_entry_json "$family_name" "$scenario" "$replica" "failed" "$exit_code" "$command_text" "$stats_csv_path")"
          append_entry "$ENTRIES_FILE" "$entry_json"

          if [[ "$CONTINUE_ON_FAILURE" != true && "$PILOT_CONSOLIDATION_STOP_ON_FIRST_FAILURE" == true ]]; then
            REPORT_LINES+=("Stopped on failure    : family=$family_name scenario=$scenario replica=$replica exitCode=$exit_code")
            STOP_CAMPAIGN=true
          fi
        fi

        should_run_cluster_stabilization=false
        if [[ "$DRY_RUN" != true && $exit_code -eq 0 ]]; then
          should_run_cluster_stabilization=true
        fi

        if [[ "$should_run_cluster_stabilization" == true && "$NAMESPACE_OVERRIDE" != "" ]]; then
          stabilization_output="$(wait_consolidated_cluster_stabilization "$NAMESPACE_OVERRIDE" "$KUBECONFIG_PATH" "$STATISTICAL_RIGOR_STABILIZATION_TIMEOUT_SECONDS" "$STATISTICAL_RIGOR_STABILIZATION_POLL_INTERVAL_SECONDS")"
          IFS=$'	' read -r stabilization_deployments stabilization_pods stabilization_summary <<< "$stabilization_output"
          REPORT_LINES+=("Cluster stabilization : family=${family_name} scenario=${scenario} replica=${replica} deployments=${stabilization_deployments} pods=${stabilization_pods}")
        elif [[ "$DRY_RUN" != true && $exit_code -eq 42 ]]; then
          REPORT_LINES+=("Cluster stabilization : skipped for family=${family_name} scenario=${scenario} replica=${replica} because the scenario was classified as unsupported_under_current_constraints")
        elif [[ "$DRY_RUN" != true && "$NAMESPACE_OVERRIDE" != "" ]]; then
          REPORT_LINES+=("Cluster stabilization : skipped for family=${family_name} scenario=${scenario} replica=${replica} because the run did not complete successfully (exitCode=${exit_code})")
        else
          REPORT_LINES+=("Cluster stabilization : skipped for family=${family_name} scenario=${scenario} replica=${replica} because Namespace was not provided")
        fi

        if [[ "$STOP_CAMPAIGN" == true ]]; then
          break
        fi

        if (( replica_index < ${#FAMILY_REPLICAS[@]} - 1 )) && (( STATISTICAL_RIGOR_COOLDOWN_BETWEEN_REPLICAS_SECONDS > 0 )); then
          REPORT_LINES+=("Replica cooldown      : ${STATISTICAL_RIGOR_COOLDOWN_BETWEEN_REPLICAS_SECONDS}s after ${family_name}/${scenario}/${replica}")
          sleep "$STATISTICAL_RIGOR_COOLDOWN_BETWEEN_REPLICAS_SECONDS"
        fi
      fi
    done

    if [[ "$STOP_CAMPAIGN" == true ]]; then
      break
    fi

    if [[ "$DRY_RUN" != true ]] && (( scenario_index < ${#FAMILY_SCENARIOS[@]} - 1 )) && (( STATISTICAL_RIGOR_COOLDOWN_BETWEEN_SCENARIOS_SECONDS > 0 )); then
      REPORT_LINES+=("Scenario cooldown     : ${STATISTICAL_RIGOR_COOLDOWN_BETWEEN_SCENARIOS_SECONDS}s after ${family_name}/${scenario}")
      sleep "$STATISTICAL_RIGOR_COOLDOWN_BETWEEN_SCENARIOS_SECONDS"
    fi
  done

  if [[ "$STOP_CAMPAIGN" == true ]]; then
    break
  fi
done

entries_json="$("$(pilot_consolidation_require_python_command)" - "$ENTRIES_FILE" <<'PY'
import json
import sys
from pathlib import Path

entries_file = Path(sys.argv[1])
entries = []
if entries_file.exists():
    with entries_file.open("r", encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
print(json.dumps(entries, separators=(",", ":")))
PY
)"

manifest_json="$("$(pilot_consolidation_require_python_command)" - \
  "$PILOT_CONSOLIDATION_PROFILE_FILE_RESOLVED" \
  "$PILOT_CONSOLIDATION_PROFILE_ID" \
  "$PILOT_CONSOLIDATION_DESCRIPTION" \
  "$CAMPAIGN_ID" \
  "$CAMPAIGN_SCOPE" \
  "$RUN_TIMESTAMP_UTC" \
  "$BASE_URL" \
  "$OUTPUT_ROOT" \
  "$OVERALL_STATUS" \
  "$entries_json" <<'PY'
import json
import sys

payload = {
    "profileFile": sys.argv[1],
    "profileId": sys.argv[2],
    "description": sys.argv[3],
    "campaignId": sys.argv[4],
    "campaignScope": sys.argv[5],
    "createdAtUtc": sys.argv[6],
    "baseUrl": sys.argv[7],
    "outputRoot": sys.argv[8],
    "status": sys.argv[9],
    "entries": json.loads(sys.argv[10]),
}
print(json.dumps(payload, separators=(",", ":")))
PY
)"

pilot_consolidation_write_manifest "$CAMPAIGN_MANIFEST_PATH" "$manifest_json"
pilot_consolidation_write_text_report "$CAMPAIGN_TEXT_PATH" "$(printf '%s\n' "${REPORT_LINES[@]}")"
statistical_rigor_summarize_campaign "$ENTRIES_FILE" "$RIGOR_MANIFEST_PATH" "$RIGOR_TEXT_PATH" "$CAMPAIGN_ID" "$CAMPAIGN_SCOPE" "$RUN_TIMESTAMP_UTC"

echo
echo "Manifest campagna     : $CAMPAIGN_MANIFEST_PATH"
echo "Report campagna       : $CAMPAIGN_TEXT_PATH"
echo "Rigor summary         : $RIGOR_MANIFEST_PATH"
echo "Rigor report          : $RIGOR_TEXT_PATH"
echo "Stato campagna        : $OVERALL_STATUS"

if [[ "$OVERALL_STATUS" == "failed" ]]; then
  exit 1
fi
