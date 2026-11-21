# ATTACKpath Requirements

## Functional requirements

1. **Incident mapping:** For an incident description of up to 10,000 characters, return up to three ranked ATT&CK technique or sub-technique candidates, each with its ID, name, and a concise evidence-based rationale.
2. **Exact-ID lookup:** When a query contains an exact ATT&CK ID, return the matching entity and its current status rather than treating the ID as ordinary prose.
3. **Version-aware resolution:** Identify deprecated or revoked IDs and, when ATT&CK provides a replacement or successor relationship, show that relationship without silently treating IDs as interchangeable.
4. **Citations:** Include a direct ATT&CK reference URL and the source release for every returned entity.
5. **Knowledge-base coverage:** Support ATT&CK Enterprise, Mobile, and ICS data, including techniques, sub-techniques, groups, software, mitigations, and data sources from the current and two prior selected releases.

## Non-functional requirements

1. **Mapping quality:** Achieve at least 80% top-3 technique-mapping accuracy on a reviewed set of at least 50 hand-labeled incidents before describing the target as met. Report the dataset and ATT&CK release with the result.
2. **Response time:** Return a mapping response within 2 seconds at the 95th percentile under five concurrent requests on the documented local development configuration.
3. **Input handling:** Reject descriptions longer than 10,000 characters with HTTP 422; accept valid requests without storing incident text by default.
4. **Availability:** Maintain at least 99% monthly availability for the deployed API, excluding announced maintenance.
5. **Verification:** Run automated API tests for every functional requirement in CI before release; every returned entity must have a valid ID and a non-empty source reference.
