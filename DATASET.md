# Dataset: ATTACKpath

Maps an incident description or log snippet to MITRE ATT&CK tactics, techniques and mitigations, citing the exact source document.

- **Start target:** Enterprise matrix: all techniques + sub-techniques (about 800 objects)
- **Full target:** Enterprise + Mobile + ICS + groups + software + mitigations, 3 ATT&CK versions (2,500+ objects)
- **Collected by:** `scripts/fetch.py` as `examate-student-bot/0.1` ([contact](https://github.com/antony-jude/prince28-sec01-attackpath)); robots.txt is checked, concurrency is capped at four, and each host has a delay.

## Where the documents come from

- [MITRE ATT&CK](https://attack.mitre.org/)
- [MITRE ATT&CK STIX data](https://github.com/mitre-attack/attack-stix-data)

## Terms I follow

MITRE ATT&CK terms of use allow reuse with attribution to The MITRE Corporation. Every source row records the terms in `data/sources.csv`, and every manifest record preserves that licence text.

- Every answer links to the original document.
- No personal data is collected.

<!-- generated:start -->
| Source | Files | Bytes | Pages | Licence |
| --- | ---: | ---: | ---: | --- |

| mitre-attack | 10 | 57,574,105 | 10 | MITRE ATT&CK terms of use; attribution to The MITRE Corporation |

**Collected:** files=10, pages=10, bytes=54.91 MB.

The manifest is append-only and stores URL, source, licence, content type, size, SHA-256, and fetch status.
<!-- generated:end -->

## Known gaps

- The first corpus contains the current Enterprise STIX export and ten focused technique pages; Mobile, ICS, groups, software, mitigations, and two older ATT&CK releases remain future expansion work.
- Some technique pages are HTML references rather than extracted STIX objects. The Friday worker will normalize all objects into the database before embedding.
- A full three-version corpus is estimated from measured files and pages in `docs/CAPACITY.md`; the estimate should be refreshed after the remaining families are fetched.
