## Efficiency rules
- Never repeat a tool call with the same arguments. If a call did not help, change approach.
- Locate before reading: use search_similar_code / get_code_neighbors or a targeted grep first.
- Read only the line ranges you need; do not re-read a range you have already seen unless you edited it.
- Run only the targeted test for the issue, not the full suite.
- Once the targeted test passes, clean up scratch files and call submit_patch.
