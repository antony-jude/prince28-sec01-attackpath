# Capacity plan: ATTACKpath

Full corpus target: Enterprise + Mobile + ICS + groups + software + mitigations, 3 ATT&CK versions (2,500+ objects).

<!-- generated:start -->
### Measured corpus

- Files: **10**
- Pages: **10**
- Downloaded size: **54.91 MB**
- Measured source units: **26,708** (STIX objects plus HTML documents)
- Measured tokens: **10,562,080**
- STIX objects: **26,699**
- STIX tokens: **9,988,185**
- Measured tokens per STIX object: **374.1**

### Full-corpus estimate

- Target files: **2,500**
- Estimated pages: **2,500**
- Estimated source units: **26,708**
- Estimated tokens: **9.99 M**
- Estimated chunks at 500 tokens: **19,984**
- Embedding estimate at $0.20/1K tokens: **Rs 380**
- Vectors at 1024 float32 dimensions: **78.1 MB**

Tokens are estimated from compact JSON characters / 4 for each STIX object (and
HTML characters / 4 for each focused page). Regenerate this report when more
source families arrive.
<!-- generated:end -->

## What I conclude

1. **Is embedding cost a problem?** No for the measured target: the estimate is a small one-time cost at the selected embedding price, but it should be rechecked when the full three-version export is downloaded.
2. **Do the vectors and text fit in free Postgres?** The text and metadata fit comfortably; vectors are the larger item and should be compared with the current database quota before enabling production embeddings.
3. **Least certain number:** the character-to-token approximation. It is deterministic and measured per STIX object, but should be recalculated with the production tokenizer before embedding.
4. **If the corpus grows 10 times:** keep raw files in object storage and batch embeddings rather than placing source files in Postgres. Partition the manifest and index by ATT&CK release so refreshes remain incremental.
