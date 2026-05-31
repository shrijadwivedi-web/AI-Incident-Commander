# Project Context — AI Incident Commander

## Project
**Project:** AI Incident Commander

## Goal
An AI-powered SRE platform that ingests logs, metrics, and traces, detects incidents, performs root-cause analysis, and generates postmortems.

## Tech stack
- **FastAPI**
- **PostgreSQL**
- **Kafka**
- **Qdrant**
- **Prometheus**
- **Grafana**
- **Next.js**
- **Docker**
- **Kubernetes**

## Architecture style
- **Microservices**
- **Event-driven**
- **Clean Architecture**

## What this repository is
**AI Incident Commander** is an autonomous SRE co-pilot that helps on-call engineers and incident commanders reduce MTTR by ingesting alerts, correlating telemetry, proposing root-cause hypotheses, and guiding safe, human-in-the-loop actions.

This file is the “entry point” for contributors and AI agents: it summarizes the product intent, scope boundaries, and where to find the canonical docs.

## Why it exists (problem statement)
Production incidents in modern cloud-native systems require responders to sift through fragmented signals (logs, metrics, traces, deploy history) across multiple tools. This increases cognitive load, slows triage, and keeps runbooks and tribal knowledge out of reach when it matters most.

## Target users
- **On-call Engineer (SRE/Dev)**: needs rapid context, safe diagnostics, and suggested next steps.
- **Incident Commander**: needs clear status, timelines, and stakeholder-ready updates.
- **Platform Administrator**: needs security guardrails, auditability, and policy compliance.

## Core capabilities (high level)
- **Alert ingestion & correlation** across sources into an “Incident Session”.
- **Context enrichment** (recent logs/metrics/deploy changes) for impacted services.
- **AI-assisted diagnostics** with top hypotheses and retrieval from historical incidents/runbooks.
- **Safe runbook execution** with guardrails and explicit approval for state-changing actions.
- **Communication automation** (ChatOps + periodic summaries + drafted stakeholder comms).
- **Post-incident artifacts** (timeline + post-mortem draft + ticket export).

## Non-goals / guardrails (scope boundaries)
- **No autonomous destructive actions by default**. State-changing operations must be explicitly approved (and may require stronger approvals based on severity).
- **No permission escalation**. All actions execute under the caller’s RBAC/IAM identity.
- **Privacy-first telemetry handling**. Sensitive data should be masked before leaving trusted boundaries.

## Success metrics (examples)
- Reduced **MTTR** and **time-to-context**
- Higher **RCA accuracy** and **command acceptance rate**
- Faster **post-mortem drafting**

## Canonical documents
- **PRD**: `docs/PRD.md`
- **Architecture**: `docs/architecture.md`
- **Tech decisions**: `docs/tech-decisions.md`
- **Milestones / roadmap**: `docs/milestones.md`

## How to use this doc
If you’re:
- **New to the repo**: read `docs/PRD.md` then `docs/architecture.md`.
- **Implementing a feature**: confirm it aligns with the guardrails above; record noteworthy trade-offs in `docs/tech-decisions.md`.
- **Building agent behaviors**: treat “guardrails” as hard requirements; ensure every action is auditable and least-privilege.
