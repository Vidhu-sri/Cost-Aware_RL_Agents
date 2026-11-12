---
license: cc-by-4.0
task_categories:
- text-generation
language:
- en
tags:
- code
- software-engineering
- swe-bench
- nebius
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train-*
dataset_info:
  features:
  - name: base_commit
    dtype: string
  - name: created_at
    dtype: string
  - name: image_name
    dtype: string
  - name: instance_id
    dtype: string
  - name: interface
    dtype: string
  - name: language
    dtype: string
  - name: license
    dtype: string
  - name: patch
    dtype: string
  - name: pr_description
    dtype: string
  - name: problem_statement
    dtype: string
  - name: repo
    dtype: string
  - name: test_patch
    dtype: string
  - name: FAIL_TO_PASS
    list: string
  - name: PASS_TO_PASS
    list: string
  - name: install_config
    struct:
    - name: base_image_name
      dtype: string
    - name: docker_specs
      struct:
      - name: _variant
        dtype: string
      - name: bazel_version
        dtype: string
      - name: bun_version
        dtype: string
      - name: cargo_version
        dtype: string
      - name: deno_version
        dtype: string
      - name: docker_version
        dtype: string
      - name: erlang_version
        dtype: string
      - name: gcc_version
        dtype: string
      - name: go_version
        dtype: string
      - name: helm_version
        dtype: string
      - name: java_version
        dtype: string
      - name: jdk_version
        dtype: string
      - name: llvm_version
        dtype: string
      - name: lua_version
        dtype: string
      - name: luajit_version
        dtype: string
      - name: neovim_version
        dtype: string
      - name: node_version
        dtype: string
      - name: npm_version
        dtype: string
      - name: nvim_version
        dtype: string
      - name: pnpm_version
        dtype: string
      - name: python_image
        dtype: string
      - name: python_version
        dtype: string
      - name: redis_version
        dtype: string
      - name: ruby_version
        dtype: string
      - name: rust_version
        dtype: string
      - name: rustc_version
        dtype: string
      - name: solana_version
        dtype: string
      - name: sqlite_version
        dtype: string
    - name: install
      list: string
    - name: log_parser
      dtype: string
    - name: test_cmd
      dtype: string
  - name: meta
    struct:
    - name: llm_metadata
      struct:
      - name: code
        dtype: string
      - name: confidence
        dtype: float64
      - name: detected_issues
        struct:
        - name: B1
          dtype: bool
        - name: B2
          dtype: bool
        - name: B3
          dtype: bool
        - name: B4
          dtype: bool
        - name: B5
          dtype: bool
        - name: B6
          dtype: bool
      - name: difficulty
        dtype: string
      - name: external_urls
        list: string
      - name: intent_completeness
        dtype: string
      - name: pr_categories
        list: string
      - name: reasoning
        dtype: string
      - name: test_alignment_issues
        list: string
    - name: num_modified_files
      dtype: int64
    - name: num_modified_lines
      dtype: int64
    - name: pr_author
      dtype: string
    - name: pr_labels
      list: string
    - name: pr_url
      dtype: string
  splits:
  - name: train
    num_bytes: 2556647025
    num_examples: 32079
  download_size: 2262924633
  dataset_size: 2556647025
---

# SWE-rebench-V2

## Dataset Summary

SWE-rebench-V2 is a curated dataset of software-engineering tasks derived from real GitHub issues and pull requests. The dataset contains 32,079 samples covering Python, Go, TypeScript, JavaScript, Rust, Java, PHP, Kotlin, Julia, Elixir, Scala, Swift, Dart, C, C++, C#, R, Clojure, OCaml, and Lua.
For log parser functions, base Dockerfiles, and the prompts used, please see https://github.com/SWE-rebench/SWE-rebench-V2  
The detailed technical report is available at [“SWE-rebench V2: Language-Agnostic SWE Task Collection at Scale”](https://arxiv.org/abs/2602.23866).

❗ **Benchmark overlap:** We excluded repositories from the original SWE-bench, but did not explicitly filter other benchmarks. Before training, check the [overlap analysis and task IDs](https://github.com/raimondasl/agentleak#case-3-swe-rebench-v2-vs-multilingual-swe-benchmarks) and exclude tasks that overlap with your evaluation benchmarks.

## Quick Start

```python
from datasets import load_dataset

ds = load_dataset("nebius/SWE-rebench-V2", split="train")
print(len(ds))  # 32079
```

## Dataset Structure

| Field | Type | Description |
|---|---|---|
| `instance_id` | `string` | Unique identifier for the instance |
| `repo` | `string` | GitHub repository in `owner/repo` format |
| `base_commit` | `string` | Git commit SHA of the base before the fix |
| `patch` | `string` | The gold patch that resolves the issue |
| `test_patch` | `string` | Diff adding or modifying tests that verify the fix |
| `problem_statement` | `string` | Issue description the patch addresses |
| `pr_description` | `string` | Full pull request description |
| `created_at` | `int64` | Unix timestamp (milliseconds) of the issue/PR creation |
| `image_name` | `string` | Docker image name used for the evaluation environment |
| `language` | `string` | Primary programming language of the repository |
| `interface` | `string` | Description of the code interface changed by the patch |
| `license` | `string` | SPDX license identifier of the repository |
| `FAIL_TO_PASS` | `list[string]` | Test IDs that fail before the patch and pass after |
| `PASS_TO_PASS` | `list[string]` | Test IDs that pass both before and after the patch |
| `install_config` | `struct` | Configuration needed to reproduce the test environment |
| `meta` | `struct` | Metadata and LLM-generated quality annotations |

# License
The dataset is licensed under the Creative Commons Attribution 4.0 license. However, please respect the license of each specific repository on which a particular instance is based. To facilitate this, the license of each repository at the time of the commit is provided for every instance.


# Citation

```bibtex
@misc{badertdinov2026swerebenchv2languageagnosticswe,
      title={SWE-rebench V2: Language-Agnostic SWE Task Collection at Scale}, 
      author={Ibragim Badertdinov and Maksim Nekrashevich and Anton Shevtsov and Alexander Golubev},
      year={2026},
      eprint={2602.23866},
      archivePrefix={arXiv},
      primaryClass={cs.SE},
      url={https://arxiv.org/abs/2602.23866}, 
}