# OverCR

$: ~/summon

     
                                 ▀█
             ████     ████       ▀█▓▀▀▓▄            █▒
              █▓▀█▐█ ▓███         ▀█▒▓▒░▓░  ▄██▄  ███▒
                █▄▒█▒█▌            ▀▒▐▒ ▒ ▀█▀███▀▄▌▄█
                 ▓▒██░               ▓░░░▒░▒▒████▒▒▀
                 ▀▓█▓                 ░▄▒ ▒▒▐▀▒██▄░
                 ▒▀█▌                    ▒░▒▒▒░█▓▒        ▄▄
                 ░▓█▒                   ▀░ ▀▓█░██░ ░ ▄█▌▒█▄▌▀▀▒▒▒
               █▌▄▄██░█           ▒   ▄▄░▒▄▄▀▌▀▀▒▐████████████▒▒
              ▒█▄▓███▒         █▓▓▄▄▀ ▐░░▓▒▓███▀█▐█▐░▒██▀▄████▓▄▒
              ░░▀▒▀██       ░█████▀ ▒▄▓██████████▒▀▀██ ▓▓▓█▀████▓▒
               ░  ░█░▐░    ▀▀▀▀▐▒ ▐▓██████████████▓░  ░░ ░██████▌▒░
           ▄  ▐  ▐▓█▓▐█▌▄▄▀▀▀▒░  ▄▓▒▀██████████▓██▓▒  ▐▒▐▄░░     ▀▀░
     ▐█▌▓█▌▐███████████████▌▀▒░  ░ ▐▒█▓▓██▓█▓█▓▓███▌▒  ▓█▄▀▌▒▀█▓▀▒
       ▓    ▐ ▄░ ▐▒████████████▀ ░░▐░▒▓▀▄▓▒▒▒▒▓██▓▒▌░   ▐▓▀░▓▄░▒▓▀▀▒
            ▀▒█░▒▒▐███▓██▌  ░▐▒  ░░░▐▒▒▌▒▒▒▀▓▀▒▓▒▒▒░     ▐█▓░▒██▓▓▄▒▒░
             █▒▌▒▒▒█▓█▌██         ▒ ▒▒░░▀▀█▓▄▒▓▌▄▒░░       ▀▓▌▄░▒▀▀▀█▒▒▀▄
             █▒▌▒▒▒███▌██░        ▐  ▒▒▒▒▒▒░▒░▄▒▄▐░     ▒    ▀███▄█▒░▒▀▒░▒▀▐
             █░▌▓▒▒█▓████     ░   ░░▒▐▒▓███▄▓█▓█▓▌▒░   ░    ░░░▀█▓▓▓▒░░▒  ░▐
             █▒▌▒▒▌███▌██ ░    ░   ░░▒▐▒▓███▄▓█▓█▓▌▒░   ░    ░░░▀█▓▓▓▒░░▒  ░▐
             █░▌▓▒▒█▓████     ░  ▒▐▒▒░▀█▒▓▓▓█▀▀▀▓█▌▀▐░   ░  ▒▌███░▐▀▓▒▌▒ ▒    ░
             █▒▌▒▒▒█▓████     ░░░░▐░▒░▄░▒▀░░▓▓██▓███▒░   ░  ░▄█▓█▓░  ▒▀▌▓▄▐▒
             █▒▌▒▒▒█▓▓▌██     ░ ▒▌ ░ ░▒░▐▒█▒ ▀▓██▓██▓▒░     ░▌██▓▌░   ▐▒▒▓▒ ░▒░
             █▒▌▒▒▐██▓▌██     ░▄░░ ▒ ░▐█▓░█▓ ▀▓█████▓▒▒░    ▄▒██▓▒     ▐▌▒░▒▒
             █▒▌▒▒▒█▓▓▌██    ░░░░ ▐▒░▒▓▒▌░▓▌  ▒ ░░░ ▀░░░░ ░▄▐▒▄▌▀▐      ▐▌▒ ░▒░

**Operational Vigilance, Execution, Recovery, Command & Routing**

Pronounced **Overseer**. OverCR is a Hermes-first operational substrate for local AI workspaces.

**Version:** v0.0.3-alpha  
**Status:** Experimental clean-core release. Not production-ready.

## What OverCR Is

OverCR is not a model, SaaS product, or Open WebUI fork. It is a filesystem-grounded doctrine and workspace structure that gives an AI agent durable operational identity, governance rules, route memory, release discipline, and boot continuity.

The core idea is simple:

```text
files > memory > chat
```

The filesystem is the source of truth. Chat history is useful context, but it is not authoritative.

## Primary Runtime: Hermes

OverCR is designed to run primarily in **Hermes** in the terminal. Hermes is the main supported interface and the intended field runtime.

Open WebUI is optional and secondary. It can act as a browser command room or visual layer on top of the same OverCR workspace, but it does not automatically share state with Hermes unless both runtimes are pointed at or synced with the same files.

Other routers, harnesses, and model providers can be used at the operator's discretion. The substrate is provider-agnostic.

## Runtime Model

```text
Operator
  -> Hermes terminal runtime, primary
  -> optional Open WebUI browser layer, secondary
  -> OverCR filesystem substrate
  -> local, cloud, or hybrid model provider
```

Hermes executes the live command-center route. Open WebUI can review files, prompts, and outputs. OverCR is the durable doctrine and state layer beneath both.

This release includes a lightweight Hermes context file and preflight check so Hermes sessions can start with the OverCR workspace expectations visible. These files make the operating posture explicit; they are not a replacement for Hermes' own configuration and approval features.

## Governance Model

OverCR follows **research autonomy with execution governance**.

Agents may:

- search
- read public information
- summarize
- enrich
- score
- draft
- organize
- create task records

Agents may not, without explicit human approval:

- send emails
- submit forms
- message people or businesses
- make calls
- book appointments
- purchase anything
- bypass access controls
- perform destructive filesystem actions

This is doctrine, not a preference.

Hermes may provide native prompts or guardrails for some command risks. OverCR's governance boundary is broader than terminal safety, so outbound and irreversible actions still require operator approval even when no runtime prompt appears.

## Source-of-Truth Hierarchy

1. Filesystem state in the OverCR workspace
2. Config files, route memory, audit/checkpoint files when present
3. Hermes session memory
4. Chat history

When there is conflict, trust durable files over chat.

## Quick Start

```bash
git clone <repo-url> overcr
cd overcr
export OVERCR_ROOT="$(pwd)"
bash overcr-hermes-preflight.sh
bash overcr-hq-localboot.sh
```

Inside Hermes, start with:

```text
Boot OverCR HQ from prompts/hq_compact_boot.md
```

Run a local verification check:

```bash
bash HQ_BOOT_VERIFICATION.sh
```

See [INSTALL.md](INSTALL.md) for full setup.

## Directory Structure

```text
overcr/
├── soul.md
├── soul_reference.md
├── AGENTS.md
├── overcr_state.json
├── overcr-hq-localboot.sh
├── overcr-hermes-preflight.sh
├── HQ_ROUTE_MARKER
├── HQ_BOOT_MANIFEST.md
├── HQ_BOOT_VERIFICATION.sh
├── README.md
├── INSTALL.md
├── RUNTIME_MODEL.md
├── PUBLIC_BOOTSTRAP.md
├── RELEASE_NOTES_v0.0.3.md
├── CLEAN_STRUCTURE_REPORT.md
├── configs/
│   └── hermes-profiles.md
├── prompts/
├── memory/routes/hq/
├── tasks/
├── workspace/
└── tui/
```

Runtime logs, saved sessions, checkpoints, databases, secrets, and local release artifacts are intentionally excluded by `.gitignore`.

## CryER

CryER stands for **Crawling Reputation, Yield, Evidence & Recon**.

CryER is a planned read-only public-recon subagent. It is specified but not implemented in this release. Its operating principle is:

```text
eyes on, hands off, no footprint
```

CryER may inspect public information and return structured recon. It may not log in, post, message, submit forms, bypass controls, or collect private personal data.

## What Is Included

- OverCR identity doctrine
- Hermes-first boot flow
- Hermes context file and profile notes
- Hermes preflight check
- HQ route scaffolding
- route memory directories
- provider-agnostic runtime model
- governance and approval boundaries
- filesystem-first authority model
- clean-core release documentation

## What Is Not Included Yet

- running CryER subagent
- Open WebUI sync bridge
- automatic session ingestion pipeline
- durable task graph implementation
- automatic Hermes policy enforcement beyond documented profile checks
- production installer
- CI/CD
- hosted service

## License

See [LICENSE](LICENSE). Current status: license TBD, no open-source license granted yet.
