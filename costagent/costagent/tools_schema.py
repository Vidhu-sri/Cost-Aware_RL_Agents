"""JSON schemas for the 9 swegemma tools (from HARNESS_README section 6).

Used only to render training contexts with the chat template when exact
proxy captures are not available. Order and wording follow the README.
"""

def _fn(name, desc, props, required):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props, "required": required}}}

TOOLS = [
    _fn("run_command", "Executes a shell command in /bin/bash -c inside /workspace.",
        {"command": {"type": "string"}}, ["command"]),
    _fn("submit_patch", "Stages untracked file intents and captures git diff HEAD from /workspace.", {}, []),
    _fn("get_status", "Returns live budget consumption and patch status.", {}, []),
    _fn("read_file", "Reads a file from /workspace with 1-indexed inclusive line slicing.",
        {"filepath": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}},
        ["filepath"]),
    _fn("edit_file", "Replaces old_string with new_string in an existing non-empty file inside /workspace.",
        {"filepath": {"type": "string"}, "old_string": {"type": "string"},
         "new_string": {"type": "string"}, "allow_multiple": {"type": "boolean"}},
        ["filepath", "old_string", "new_string"]),
    _fn("write_file", "Creates or overwrites a file at /workspace/<filepath>.",
        {"filepath": {"type": "string"}, "content": {"type": "string"}}, ["filepath", "content"]),
    _fn("get_code_neighbors", "Finds incoming and outgoing neighbors of a symbol in the repository graph.",
        {"node": {"type": "string"}, "edge_type": {"type": "string"}, "max_neighbors": {"type": "integer"}},
        ["node"]),
    _fn("search_similar_code", "Finds top-k graph nodes most similar to a symbol name.",
        {"query": {"type": "string"}, "k": {"type": "integer"}}, ["query"]),
    _fn("get_code_subgraph", "Extracts the induced subgraph for a list of symbols.",
        {"nodes": {"type": "array", "items": {"type": "string"}}}, ["nodes"]),
]

FREE_TOOLS = {"submit_patch", "get_status"}
EDIT_TOOLS = {"edit_file", "write_file"}
GRAPH_TOOLS = {"get_code_neighbors", "search_similar_code", "get_code_subgraph"}
