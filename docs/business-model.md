# Empneon Business Model

**Version:** 0.2

## Product Position

Empneon is infrastructure for developers building simulation, sandbox, management,
role-playing, and social games with persistent consequential agents.

The initial customer profile is an indie or AA team operating roughly 20-200 important
NPCs under strict latency, hardware, or inference-cost constraints.

The Sims 4 community is the first demonstration and distribution wedge. It is not the
only supported game and is not the primary source of revenue. A second adapter must
prove portability before Empneon is marketed as a general platform.

## Customer Problem

Studios need more than natural dialogue. They need:

- predictable inference cost and game performance
- authorial control and game-rule validation
- persistent identity and social consequences
- model and deployment flexibility
- debugging, attribution, replay, and evaluation
- graceful behavior during model failure or resource pressure

Empneon should sell reliability and control for simulated societies, not a claim that
NPCs are generally intelligent.

## Defensible Position

Local-first and provider-agnostic deployment are requirements, not sufficient moats.
The intended differentiation is measurable:

> More coherent persistent agents per unit of latency, memory, and inference cost,
> with developer-visible causality and control.

Potential defensibility comes from the adaptive scheduler, epistemic simulation,
benchmark corpus, integration experience, and production observability data.

## Revenue Model

### Apache-Licensed Core

Empneon Core remains Apache 2.0 and permits commercial use. Studios do not owe a fee
merely for embedding the core.

### Hosted Runtime

Optional managed provider routing, scheduling, persistence, and observability. Build
this only after design partners demonstrate demand. Pricing should emphasize
predictability, with inference cost passed through or clearly metered.

### Developer and Operations Tooling

Potential paid tooling includes:

- agent and belief timelines
- decision explanations and replay
- CLOD, latency, token, and memory heatmaps
- scenario evaluation and regression runs
- production alerts and managed observability

### Integration and Support

Paid adapter work, architecture reviews, performance tuning, training, enterprise
self-hosting support, and service-level agreements can generate the earliest revenue.

## Validation Gates

Do not build billing or a broad cloud platform before:

1. A Sims 4 vertical slice produces persistent autonomous social consequences.
2. At least 100 testers use the demonstration repeatedly.
3. At least 15 target developers have been interviewed.
4. A second adapter works without game-specific changes to the core model.
5. Three studios participate as design partners.
6. At least one studio pays for integration, tooling, or support.

## Go-To-Market Sequence

### Prove

- Ship the Sims 4 reference experience.
- Publish SocietyBench results and raw hardware measurements.
- Demonstrate provider replacement between local and hosted models.

### Prove Portability

- Build the selected small Godot 4 portability adapter before considering Unity, Roblox,
  or other integrations.
- Publish an adapter guide and contract tests.

### Sell Services and Tooling

- Recruit indie and AA design partners.
- Charge for integration, debugging tools, and production support.

### Host Repeated Demand

- Add hosted scheduling and observability only after customers request managed
  operation and unit economics are known.

## What To Avoid

- Charging modders for the Apache-licensed core
- Claiming commercial license revenue from Apache-licensed code
- Building adapters for many games before proving the second one
- Building cloud billing before customer validation
- Competing on generic NPC dialogue
- Publishing unmeasured scalability or hardware claims

## Business Success Measures

- active integrations and retained developers
- time required to build an adapter
- percentage of cognition resolved without expensive inference
- predictable cost per simulated agent-hour
- benchmarked improvement over a simple baseline
- paid design partners and support renewals
