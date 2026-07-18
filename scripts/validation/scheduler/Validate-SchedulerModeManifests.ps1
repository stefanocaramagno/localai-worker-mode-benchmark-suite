param(
  [string] $RepoRoot = ".",
  [string[]] $ScanRoot = @("infra/k8s/compositions/resource-aware-scheduler"),
  [ValidateSet("auto", "default", "loadaware", "networkaware")]
  [string] $Mode = "auto",
  [string] $ExpectedSchedulerName = "scheduler-plugins-scheduler",
  [switch] $RenderKustomize,
  [switch] $RequireRender,
  [switch] $AllowSourceOnly,
  [switch] $Json
)

$ErrorActionPreference = "Stop"

$Python = "python"
$ScriptPath = Join-Path $RepoRoot "scripts/validation/scheduler/validate-scheduler-mode-manifests.py"

$Arguments = @(
  $ScriptPath,
  "--repo-root", $RepoRoot,
  "--mode", $Mode,
  "--expected-scheduler-name", $ExpectedSchedulerName
)

foreach ($Root in $ScanRoot) {
  $Arguments += @("--scan-root", $Root)
}

if ($RenderKustomize) { $Arguments += "--render-kustomize" }
if ($RequireRender) { $Arguments += "--require-render" }
if ($AllowSourceOnly) { $Arguments += "--source-only" }
if ($Json) { $Arguments += "--json" }

& $Python @Arguments
exit $LASTEXITCODE
