# ATTACKpath

Maps an incident description or log snippet to MITRE ATT&CK tactics, techniques, and mitigations, with links to the source technique pages.

**Status:** Local Docker Compose stack, migrations, sample ATT&CK records, and unit/integration test workflows. Live URL planned for Day 5.

## Who it's for

An L1 SOC analyst at a managed security provider in Guindy, Chennai, triaging about 200 alerts a night for bank and hospital clients.

## The problem

ATT&CK offers a large, versioned catalog, and triage analysts often need to connect an unstructured alert to a precise technique quickly. The manual work is slow, especially when an alert's wording differs from the catalog or an older alert names an ID that has since been deprecated or replaced. That delay also makes it harder to find relevant mitigations and telemetry sources consistently. ATTACKpath will narrow the search and show evidence-backed links so analysts can verify suggestions rather than treating them as definitive.

## Data sources

MITRE ATT&CK Enterprise, Mobile, and ICS knowledge bases (STIX 2.1 JSON): techniques, sub-techniques, groups, software, mitigations, and data sources for the current and two older selected releases.

- [MITRE ATT&CK](https://attack.mitre.org/)
- [MITRE ATT&CK STIX data](https://github.com/mitre-attack/attack-stix-data)
- Follow MITRE ATT&CK terms of use and attribution requirements.

The starter records in `data/sample_records.json` are sourced from the MITRE ATT&CK Enterprise v20.1 STIX 2.1 release. `data_sources`, `mitigations`, and `detection` are populated from the linked data components, mitigation relationships, and detection analytics in that release.

## Hardest problem (my interview story)

IDs change between releases: techniques can be deprecated, revoked, or split into sub-techniques (for example, T1086 PowerShell was revoked and replaced by T1059.001). Answers must resolve old IDs to the current technique, while exact-ID questions such as `T1059.001` need exact lookup because embeddings can treat IDs as noise.

## Signature feature

**Kill-chain strip:** paste an incident story and see the matched techniques across the 14 tactics, each linked to its cited page.

## Target metric

At least 80% top-3 technique-mapping accuracy on a reviewed 50-incident test set with hand-labeled technique IDs.

## Run locally in one command

You need Docker Desktop running. From a fresh clone:

```bash
docker compose up --build
```

This starts Postgres with pgvector, Redis, runs migrations, loads the sample data once, and starts the API.

- API docs: http://localhost:8000/docs
- Liveness: http://localhost:8000/health
- Readiness: http://localhost:8000/ready

Stop with `Ctrl+C`, then `docker compose down`. Use `docker compose down -v` to also delete the database volume.

## Develop and test

| Task | Mac / Linux | Windows |
|---|---|---|
| Run the API with reload | `make dev` | `uv run poe dev` |
| Unit tests (no network) | `make test` | `uv run poe test` |
| Integration tests (Docker Compose running) | `make test-integration` | `uv run poe test-integration` |
| Coverage report | `make cov` | `uv run poe cov` |
| Lint and format check | `make lint` | `uv run poe lint` |

On Windows, `./tasks.ps1` also provides `up`, `down`, `unit`, `integration`, `test`, `coverage`, and `lint` shortcuts; its test commands delegate to the Poe tasks above.

The sample ATT&CK records are a small starter set, not a scored evaluation dataset.
