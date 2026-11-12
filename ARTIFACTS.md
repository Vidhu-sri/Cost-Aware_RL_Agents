# Large artifacts

The private Hugging Face repository [silvix9/Cost-Aware-Gemma](https://huggingface.co/silvix9/Cost-Aware-Gemma/tree/01a1217dfcbf6603be9b456086528b0f80a282f0) stores the trained adapters and the downloaded training metadata separately from the GitHub source tree. Access requires authorization for that repository.

Pinned artifact revision: `01a1217dfcbf6603be9b456086528b0f80a282f0`.

| Artifact | Hugging Face path | Bytes |
| --- | --- | ---: |
| A2 RFT adapter | `rft-a2/adapter_model.safetensors` | 244982384 |
| DPO epoch 5 adapter | `dpo-epoch-005/adapter_model.safetensors` | 244982384 |
| SDPO contrast epoch 5 adapter | `sdpo-contrast-epoch-005/adapter_model.safetensors` | 244982384 |
| SWE-rebench V2 training metadata | `source-artifacts/swe-rebench-work/metadata/train.parquet` | 428839266 |

Each adapter directory contains its PEFT configuration. The root `manifest.json` records adapter checksums. `source-artifacts/dataset-provenance.json` records the dataset source, pinned revision, license declaration and checksum. The dataset is byte-identical to `nebius/SWE-rebench-V2`, revision `10483de0f50fe5da545942705a76c6150171af7f`, file `data/train-00000-of-00001.parquet`. Its original project-relative location is `swe-rebench-work/metadata/train.parquet`.

The base model is [google/gemma-4-31B-it-qat-w4a16-ct](https://huggingface.co/google/gemma-4-31B-it-qat-w4a16-ct); full base-model weights are not duplicated here. Use the original model's access requirements and terms.

CUDA compatibility libraries, baseline ZIP bundles, logs, result directories, and the original base-model metadata remain preserved in the local workspace but are not part of this source publication. The CUDA/runtime archive was not uploaded to Hugging Face. Obtain runtime dependencies from their original providers when configuring a new host. Local absolute symlinks for `costagent/artifacts` and `costagent/results` are excluded; configure these paths for your own workspace.

The publisher harness is recorded as a submodule at commit `c71902a8cf8d2b725f63d51f199f4d3e56f68d2d`. Initialize it with `git submodule update --init swe-rebench-work/publisher-harness`.

The training metadata contains reference patches and grading metadata. Keep it outside agent-visible inputs and task containers. All original local results and checkpoints were retained during publication.
