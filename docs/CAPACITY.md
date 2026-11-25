# Capacity plan: ATTACKpath

Full corpus target: Enterprise + Mobile + ICS + groups + software + mitigations, 3 ATT&CK versions (2,500+ objects).

<!-- generated:start -->
### Measured corpus

- Files: **10**
- Pages: **10**
- Downloaded size: **54.91 MB**
- Measured tokens per page: **750**

### Full-corpus estimate

- Target files: **2,500**
- Estimated pages: **2,500**
- Estimated tokens: **1.88 M**
- Estimated chunks at 500 tokens: **3,750**
- Embedding estimate at $0.20/1K tokens: **Rs 71**
- Vectors at 1024 float32 dimensions: **14.6 MB**

The estimate is based on the measured files above and should be regenerated when more
source families arrive.
<!-- generated:end -->

## What I conclude

1. **Is embedding cost a problem?** No for the measured target: the estimate is a small one-time cost at the selected embedding price, but it should be rechecked when the full three-version export is downloaded.
2. **Do the vectors and text fit in free Postgres?** The text and metadata fit comfortably; vectors are the larger item and should be compared with the current database quota before enabling production embeddings.
3. **Least certain number:** token count per page, because HTML navigation and JSON field repetition vary. I will measure a larger mixed sample after the full corpus arrives.
4. **If the corpus grows 10 times:** keep raw files in object storage and batch embeddings rather than placing source files in Postgres. Partition the manifest and index by ATT&CK release so refreshes remain incremental.
