# 10. Statistical Rigor and Repeatability

## Objective

This runbook defines the minimum statistical rigor and repeatability rules required to treat benchmark results as operationally credible and analytically usable.

The purpose of this phase is not to perform advanced academic statistical analysis. The purpose is to ensure that benchmark outputs are:

- reproducible;
- internally consistent;
- sufficiently stable to support technical diagnosis;
- comparable across scenarios and sweep families.

This runbook applies after the baseline flow and pilot sweep execution logic are already in place, and before any diagnostic interpretation or phase-closure decision is made.

---

## When to Use This Runbook

Use this runbook when at least one of the following conditions is true:

- the official baseline has already been executed successfully;
- exploratory pilot sweeps have already been completed;
- consolidated pilot benchmarks are about to be executed or have just been executed;
- a validation step is needed to confirm that observed trends are not dominated by run-to-run noise;
- results must be promoted from exploratory evidence to repeatable technical evidence.

This runbook is part of the post-execution validation layer of the pipeline.

---

## Scope

This runbook covers:

- the repeatability model used by the project;
- replica execution rules;
- consistency expectations across repeated runs;
- statistical-rigor validation inputs and outputs;
- interpretation of stability summaries;
- decision rules for acceptable versus noisy scenario families.

This runbook does **not** define:

- how to deploy the workload under test;
- how to perform cluster prechecks;
- how to run smoke validation;
- how to collect raw artifacts;
- how to generate the technical diagnosis itself.

Those activities are handled in separate runbooks.

---

## Governing Principle

A benchmark result is not considered reliable only because it completed successfully once.

A result becomes operationally credible only when:

1. the same scenario is executed multiple times under the same protocol;
2. the benchmark window remains comparable across replicas;
3. the observed client-side metrics stay within an acceptable variability envelope;
4. no hidden infrastructure anomaly invalidates one or more replicas.

The statistical rigor layer exists to distinguish:

- true scenario behavior;
- transient runtime noise;
- artifacts caused by unstable cluster state;
- misleading outliers;
- formally unsupported scenarios that exceed the current frozen baseline constraints.

---

## Repository Components Involved

The statistical rigor phase is aligned with the project configuration and execution model already present in the repository.

Relevant components include:

- `config/statistical-rigor/SR1.json`
- consolidated benchmark outputs under `results/pilot/consolidated/`
- validation outputs generated during consolidated execution
- client-side benchmark metrics produced by Locust
- run manifests and scenario metadata used for grouping and comparison

The statistical rigor profile is expected to operate on the consolidated benchmark phase, not on smoke runs or on ad hoc exploratory tests. In the current implementation, the same profile also carries the cluster-stabilization parameters used by the consolidated launcher between normally completed runs, so `SR1.json` now influences both the rigor summary and the inter-run convergence checks.

---

## Preconditions

Before applying this runbook, verify that all the following conditions are satisfied:

- the benchmark family under analysis has already been executed in consolidated mode;
- all scenarios in scope were executed with a common protocol;
- warm-up and measurement windows were separated consistently;
- run identifiers and scenario metadata were recorded correctly;
- raw client-side artifacts exist for each replica;
- cluster-side artifacts were collected for each scenario family;
- no unresolved fatal deployment failure remains open.

If these conditions are not met, do not proceed with statistical-rigor validation.

---

## Repeatability Model

### Core Rule

Each scenario in a consolidated campaign must be executed more than once under the same operational conditions.

The purpose of repetition is not to maximize sample size. The purpose is to verify that the observed behavior survives controlled re-execution.

### Replica Naming Convention

A scenario is expected to be executed through a bounded set of controlled replicas, typically represented as:

- replica `A`
- replica `B`
- replica `C`

This project uses a practical engineering-oriented repeatability model rather than a large-sample experimental design.

### Why Three Replicas Matter

Three replicas are enough to detect the most common operational issues:

- one-off outlier runs;
- drift caused by unstable warm-up behavior;
- intermittent API or networking failures;
- unstable throughput under nominally identical conditions;
- latent resource contention that appears only intermittently.

Three replicas are not intended to prove deep statistical significance. They are intended to provide a minimum confidence layer before interpreting scenario trends.

---

## Consistency Requirements Across Replicas

All replicas belonging to the same scenario must keep the following dimensions unchanged:

- scenario identifier;
- model;
- worker count;
- placement policy;
- workload profile;
- concurrency and/or traffic pattern;
- warm-up duration;
- measurement duration;
- client timeout behavior;
- namespace and service target;
- execution protocol ordering.

A replica must be treated as invalid if one of these dimensions changes without explicit recording and justification.

---

## Warm-Up and Measurement Invariance

Repeatability is impossible if the benchmark protocol changes between replicas.

For every repeated run in the same scenario family, the following must remain invariant:

- deployment readiness logic;
- API smoke validation step;
- warm-up duration;
- measurement duration;
- collection timing for cluster-side artifacts;
- cleanup or cooldown policy between replicas.

If warm-up duration changes between `A`, `B`, and `C`, then the run family should not be treated as statistically coherent.

---

## Cooldown Policy

A repeatability model requires not only repeated execution, but also controlled separation between executions. In the current repository state, this separation is implemented through both cooldown windows and an explicit cluster-stabilization step between normally completed consolidated runs.

### Why Cooldown Matters

Without a cooldown window, the next replica may inherit side effects such as:

- model already fully cached in memory;
- temporary node-level CPU throttling;
- residual network or pod-level congestion;
- incomplete cleanup of ephemeral state;
- delayed restart behavior in previous components.

### Cooldown Rule

A bounded cooldown should be applied:

- between replicas of the same scenario;
- between different scenarios in the same family.

The exact values must follow the operational profile configured in the consolidated benchmark flow. The important requirement is not the numeric value itself, but its consistency across the campaign.

### Cluster Stabilization Rule

For the consolidated launcher, cooldown alone is not the only separation mechanism. After a normally completed run, the launcher also checks that the benchmark namespace has reached a stable state before continuing with the next replica or scenario.

This stabilization step is governed by parameters stored in `config/statistical-rigor/SR1.json`, including:

- `stabilizationTimeoutSeconds`;
- `stabilizationPollIntervalSeconds`.

The purpose of this step is not to reset the cluster, but to avoid treating transient post-run convergence as if it were a stable starting condition for the next run.

---

## Minimum Metric Set for Repeatability Validation

Repeatability validation must always use the same client-side metrics for every scenario family.

## Required Metrics

For each replica, collect and compare at least:

- request count;
- success count or success rate;
- failure count;
- mean response time;
- p50 response time;
- p95 response time;
- p99 response time;
- throughput.

These metrics provide the minimum necessary view to evaluate:

- stability of load generation;
- service correctness under repeated execution;
- latency consistency;
- tail-latency volatility;
- throughput drift.

Cluster-side metrics remain essential for diagnosis, but the repeatability gate is primarily centered on stable client-observed behavior.

---

## What Statistical Rigor Means in This Project

In this project, “statistical rigor” does **not** mean:

- formal hypothesis testing;
- p-value based decision making;
- inferential analysis across very large samples.

Instead, it means:

- same scenario executed repeatedly;
- same protocol applied every time;
- bounded run-to-run variability;
- explicit identification of noisy or unstable families;
- confidence that the dominant trend is not accidental.

This distinction is important. The benchmark pipeline is engineered for repeatable systems validation and scenario comparison, not for academic over-formalization.

---

## Practical Stability Questions

For every consolidated scenario family, ask the following questions.

### 1. Is load generation stable?

Check whether request count and throughput remain broadly aligned across replicas.

Large unexplained divergence can indicate:

- Locust instability;
- early termination;
- inconsistent warm-up;
- service partial failure;
- cluster-side throttling or congestion.

### 2. Is functional behavior stable?

Check whether success rate and failure count remain consistent.

If one replica shows a significantly different failure pattern, that replica may have been affected by:

- service instability;
- startup drift;
- intermittent networking issues;
- partial unschedulability;
- timeout bursts.

### 3. Is central latency stable?

Compare mean and p50 across replicas.

If central latency varies heavily, the system may be too unstable for meaningful comparison.

### 4. Is tail behavior stable?

Compare p95 and p99 across replicas.

Tail-latency volatility often reveals issues that mean values hide, such as:

- intermittent backend coordination delays;
- infrastructure contention;
- model serving jitter;
- node-level resource pressure.

### 5. Does the overall trend survive repetition?

If the same general performance ranking or degradation pattern appears across replicas, the scenario family is likely strong enough for diagnosis.

---

## Typical Causes of Poor Repeatability

If a scenario family fails the repeatability review, the most common causes are:

- incomplete cleanup between replicas;
- inconsistent readiness before warm-up starts;
- insufficient warm-up duration;
- Pending pods or delayed scheduling;
- resource pressure on one worker node;
- unstable model loading behavior;
- timeout settings too aggressive for the selected scenario;
- benchmark durations too short to smooth transient effects;
- accidental change in scenario inputs.

The purpose of the repeatability review is not only to reject results, but also to identify which operational weakness is contaminating the measurements.

---

## Recommended Execution Flow

Use the following sequence when validating repeatability for a consolidated campaign.

### Step 1 — Confirm campaign completeness

Verify that the consolidated campaign generated outputs for all expected scenarios and all expected replicas, or that any deviation is explicitly classified.

At this stage, ensure that:

- no scenario is missing unexpectedly;
- replica labels are consistent;
- manifests and metadata are present;
- no file naming ambiguity exists;
- any scenario classified as `unsupported_under_current_constraints` is explicitly recorded rather than silently counted as a normal success or a generic missing result.

### Step 2 — Confirm protocol uniformity

Inspect whether all replicas used the same benchmark structure:

- same warm-up length;
- same measurement window;
- same benchmark family;
- same workload profile;
- same scenario parameters.

### Step 3 — Inspect client-side consistency

Compare the required metrics across replicas.

Focus on:

- throughput stability;
- success rate stability;
- p95 and p99 drift;
- presence of outliers.

### Step 4 — Check for invalidating infrastructure anomalies

If one replica differs materially from the others, inspect the corresponding cluster-side artifacts.

Look for:

- restarts;
- Pending pods;
- failed scheduling;
- node pressure;
- service instability;
- unusual event traces.

### Step 5 — Classify the scenario family

Classify the family into one of the following categories:

- repeatable and usable;
- usable with caution;
- too noisy and requires rerun.

### Step 6 — Persist the summary

Generate or preserve a statistical-rigor summary that records:

- scenario family reviewed;
- replicas observed;
- metrics compared;
- overall stability outcome;
- rerun recommendation, if applicable.

---

## Interpreting the Statistical-Rigor Summary

The summary produced by the rigor step should not be read as a binary truth oracle. It is an engineering decision aid.

### Acceptable Outcome

A family can be considered acceptable when:

- all expected replicas are present for supported scenarios;
- any unsupported scenarios are explicitly identified and excluded from normal variability interpretation;
- success and failure behavior is consistent;
- latency and throughput variability stay within a reasonable envelope;
- no replica appears invalid due to cluster-side anomalies;
- the main scenario trend is preserved.

### Caution Outcome

A family may still be usable with caution when:

- one metric is slightly noisier than expected;
- p99 is volatile but central tendency remains stable;
- one replica is mildly degraded but still operationally coherent;
- the dominant ranking across scenarios remains unchanged.

In that case, the family may still support diagnosis, but the interpretation should be more conservative.

### Reject / Rerun Outcome

A family should be rerun when:

- replicas are missing without an explicit and justified classification;
- one or more replicas are invalid;
- throughput and latency drift too much to support comparison;
- failure behavior changes radically between replicas;
- cluster-side artifacts reveal infrastructure instability that invalidates the comparison.

A family should not be rerun merely because one scenario is formally classified as `unsupported_under_current_constraints`. In that case, the unsupported classification is itself part of the benchmark evidence, provided that it is consistently recorded and diagnosed.

---

## Relationship with the Technical Diagnosis Phase

The technical diagnosis phase depends on repeatable inputs.

If repeatability is weak, diagnosis risks turning noise into false explanations.

For this reason:

- do not start technical diagnosis from raw exploratory evidence alone;
- do not treat one-off anomalies as stable findings;
- do not promote unstable scenario families into phase-closure evidence.

The statistical rigor phase is the quality filter between execution and interpretation.

---

## Relationship with the Completion Gate

The completion gate should consume scenario families that have already passed a minimum repeatability review.

If the statistical rigor phase reports that a family is too noisy, that family should not count as strong evidence for phase closure.

In practical terms, the completion gate should rely on:

- scenario coverage;
- artifact completeness;
- diagnosis availability;
- repeatability status;
- explicit handling of unsupported scenarios where applicable.

A campaign with perfect coverage but poor repeatability should not be treated as complete. A campaign that includes correctly classified unsupported scenarios should be interpreted according to those classifications, not by pretending that every scenario was normally benchmarkable.

---

## Recommended Operator Checklist

Before accepting a consolidated family as stable enough for diagnosis, confirm all of the following:

- baseline and scenario metadata are correct;
- all expected replicas exist;
- protocol remained invariant across replicas;
- warm-up and measurement were separated consistently;
- request count is not abnormally divergent;
- success rate is stable;
- failure count does not reveal one-off anomalies;
- p95 and p99 remain operationally interpretable;
- no invalidating cluster-side anomaly is present;
- the dominant trend survives repetition.

If any of these checks fail, pause interpretation and investigate the cause before proceeding.

---

## Troubleshooting

## Problem: One replica is much slower than the others

### Likely causes

- delayed readiness before warm-up;
- partial pod restart;
- node-level pressure;
- benchmark started too early;
- model loading not stabilized.

### Recommended action

Check cluster-side artifacts for the affected replica and rerun the scenario if the anomaly is infrastructure-driven.

---

## Problem: Success rate differs significantly between replicas

### Likely causes

- unstable endpoint behavior;
- transient service overload;
- timeout configuration mismatch;
- deployment not fully stable before measurement.

### Recommended action

Do not accept the family as repeatable until the underlying cause is understood and corrected.

---

## Problem: p99 is highly volatile but mean and p50 are stable

### Likely causes

- tail-latency bursts;
- intermittent backend coordination overhead;
- short-lived cluster contention;
- network jitter between cooperating workers.

### Recommended action

Treat the family as usable with caution only if the volatility is bounded and the scenario ranking remains stable. Otherwise rerun.

---

## Problem: Throughput varies significantly across replicas

### Likely causes

- inconsistent Locust execution;
- partial request loss;
- uneven warm-up state;
- service degradation during one replica.

### Recommended action

Inspect the run manifests, Locust CSV outputs, and cluster-side evidence before accepting the family.

---

## Evidence Retention Requirements

The repeatability review must leave a persistent trace.

For every reviewed family, preserve at least:

- the list of scenario replicas reviewed;
- the metrics used in the comparison;
- the stability summary;
- the operator conclusion;
- rerun decisions, if any.

This is necessary for traceability and for later diagnosis or reporting.

---

## Exit Criteria

This runbook can be considered successfully completed when:

- the consolidated benchmark family has been reviewed across repeated replicas;
- minimum required client-side metrics were compared consistently;
- unstable or invalid replicas were identified explicitly;
- each scenario family was classified as acceptable, cautionary, or rerun-required;
- a persistent statistical-rigor summary is available for downstream phases.

---

## Next Step

Once repeatability validation is complete, proceed to:

- `11-technical-diagnosis.md` for evidence-based interpretation of benchmark patterns.

If the reviewed scenario families are still too noisy, return to:

- consolidated benchmark execution;
- cluster cleanup and rerun;
- benchmark protocol correction.

Do not move to diagnosis or completion-gate decisions using unstable scenario families.
