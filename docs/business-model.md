# Empneon — Business Model

## Market Position

**Target users:**
- Modders (Sims 4, Skyrim, etc.) — distribution channel, not revenue
- Indie/AA game studios — primary paying customer
- Researchers — awareness, not revenue

**Competitive landscape:**
- Inworld AI — ~$50M raised, cloud-dependent, $0.001–0.01/NPC interaction
- Convai — similar cloud model
- No open-source, local-first, game-agnostic alternative exists

**Empneon's defensible position:** Local-first + open-source + game-agnostic + no per-call cloud bill.

## Model: Open Core + Cloud

### Empneon Core — Open Source (Forever)
- Full framework, all innovations, Sims 4 adapter
- MIT or Apache 2.0 license
- Purpose: community, trust, moat against funded competitors

### Empneon Cloud — Hosted Consciousness (Revenue)
- Developers who can't/won't run local LLMs pay for hosted scheduling
- Pricing: per agent-hour or per 1000 conscious episodes
- Can undercut Inworld because CLOD means most agents never reach billable inference
- Target: indie studios, prototype builders, cloud-native game backends

### Commercial License — Studio Shipping (Revenue)
- Free for modders and non-commercial use
- Paid license for studios shipping commercial products with Empneon embedded
- Similar to: Unity runtime license, Unreal royalty model

### Support Contracts (Revenue)
- Red Hat model: open source is free, support is paid
- Target: studios integrating Empneon who need SLA, custom adapters, training

## Sequencing

**Phase 1 — Prove it (months 1–12)**
- Build framework open-source
- Ship Sims 4 adapter
- Modding community adopts it, creates content, creates noise
- Zero monetization

**Phase 2 — Expand it (months 12–24)**
- Indie devs discover it via modding community visibility
- Second game adapter (InZOI, or a Unity/Unreal template)
- Document clearly, developer experience becomes a priority
- Start commercial license conversations

**Phase 3 — Monetize it (months 18–36)**
- Launch Empneon Cloud
- Formalize commercial license
- Support contracts for serious studio integrations

## What to Avoid

- **Charging modders** — they fork it, community dies
- **Closing the license** (HashiCorp/Redis style) — destroys trust, community leaves
- **Targeting AAA first** — they build in-house, ignore you
- **Cloud-only** — defeats the local-first differentiator
- **Monetizing before community exists** — no leverage, no users

## Revenue Projections (rough order of magnitude)

Not financial advice. Illustrative only.

- 10 indie studios on commercial license at $500/year = $5K ARR (year 2)
- 50 studios + cloud users at ~$50/month average = $30K ARR (year 3)
- 1 mid-size studio support contract = $20–50K/year

This is a slow build. The modding community is the wedge. Revenue follows adoption, not the other way around.
