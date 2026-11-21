# ATTACKpath

Maps an incident description or log snippet to MITRE ATT&CK tactics, techniques, and mitigations, with links to the source technique pages.

**Status:** Day 1 foundation (uv project, FastAPI service skeleton, sample ATT&CK records, and quality gates). Live URL planned for Day 5.

## Who it's for

An L1 SOC analyst at a managed security provider in Guindy, Chennai, triaging about 200 alerts a night for bank and hospital clients.

## The problem

ATT&CK offers a large, versioned catalog, and triage analysts often need to connect an unstructured alert to a precise technique quickly. The manual work is slow, especially when an alert's wording differs from the catalog or an older alert names an ID that has since been deprecated or replaced. That delay also makes it harder to find relevant mitigations and telemetry sources consistently. ATTACKpath will narrow the search and show evidence-backed links so analysts can verify suggestions rather than treating them as definitive.

## Data sources

MITRE ATT&CK Enterprise, Mobile, and ICS knowledge bases (STIX 2.1 JSON): techniques, sub-techniques, groups, software, mitigations, and data sources for the current and two older selected releases.

- [MITRE ATT&CK](https://attack.mitre.org/)
- [MITRE ATT&CK STIX data](https://github.com/mitre-attack/attack-stix-data)
- Follow MITRE ATT&CK terms of use and attribution requirements.

## Hardest problem (my interview story)

IDs change between releases: techniques can be deprecated, revoked, or split into sub-techniques (for example, T1086 PowerShell was revoked and replaced by T1059.001). Answers must resolve old IDs to the current technique, while exact-ID questions such as `T1059.001` need exact lookup because embeddings can treat IDs as noise.

## Signature feature

**Kill-chain strip:** paste an incident story and see the matched techniques across the 14 tactics, each linked to its cited page.

## Target metric

At least 80% top-3 technique-mapping accuracy on a reviewed 50-incident test set with hand-labeled technique IDs.

## Run it locally

```powershell
uv sync
Copy-Item .env.example .env
uv run uvicorn attackpath.api.main:create_app --factory --reload
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) for the API docs. The service provides `/health`, `/ready`, `/v1/documents`, and `/v1/documents/{id}`.

## Checks

```powershell
uv run pytest
uv run ruff check .
uv run pre-commit install
uv run pre-commit run --all-files
```

`.env` is ignored by Git; commit `.env.example` only. The sample ATT&CK records are a small starter set, not a scored evaluation dataset.
