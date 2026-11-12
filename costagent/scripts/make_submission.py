#!/usr/bin/env python3
"""Copy a working submission dir and change only what an arm needs.

  make_submission.py BASE_SUB DEST [--adapter DIR] [--append-prompt FILE]
                     [--replace-prompt FILE] [--temperature 0.7]

The root agent's instruction file is found from `instruction: !include <path>`
in agent.yaml. The adapter is copied to DEST/adapters/costlora and referenced
as `adapter: costlora` on the root agent. Size is checked against 3 GiB.
"""
import argparse
import re
import shutil
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base"); ap.add_argument("dest")
    ap.add_argument("--adapter"); ap.add_argument("--append-prompt"); ap.add_argument("--replace-prompt")
    ap.add_argument("--temperature", type=float)
    a = ap.parse_args()
    base, dest = Path(a.base), Path(a.dest)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(base, dest, symlinks=False)
    agent = dest / "agent.yaml"
    y = agent.read_text()

    m = re.search(r"^instruction:\s*!include\s+(\S+)", y, re.M)
    if a.append_prompt or a.replace_prompt:
        if not m:
            raise SystemExit("agent.yaml has no `instruction: !include <file>` line; cannot edit the prompt")
        pf = dest / m.group(1)
        extra = Path(a.append_prompt or a.replace_prompt).read_text()
        pf.write_text((pf.read_text().rstrip() + "\n\n" + extra) if a.append_prompt else extra)

    if a.adapter:
        ad = dest / "adapters" / "costlora"
        ad.mkdir(parents=True, exist_ok=True)
        for f in ("adapter_config.json", "adapter_model.safetensors"):
            shutil.copy(Path(a.adapter) / f, ad / f)
        y = re.sub(r"^adapter:.*\n", "", y, flags=re.M)
        y = re.sub(r"^(model:.*\n)", r"\1adapter: costlora\n", y, count=1, flags=re.M)
        agent.write_text(y)

    if a.temperature is not None:
        mm = re.search(r"^generate_content_config:\s*!include\s+(\S+)", y, re.M)
        if not mm:
            raise SystemExit("no `generate_content_config: !include <file>` in agent.yaml; cannot set temperature")
        sp = dest / mm.group(1)
        s = sp.read_text()
        s = re.sub(r"^temperature:.*$", f"temperature: {a.temperature}", s, flags=re.M) \
            if re.search(r"^temperature:", s, re.M) else f"temperature: {a.temperature}\n" + s
        sp.write_text(s)

    size = sum(p.stat().st_size for p in dest.rglob("*") if p.is_file())
    if size >= 3 * 1024 ** 3:
        raise SystemExit(f"submission is {size / 2**30:.2f} GiB, over the 3 GiB limit")
    print(f"built {dest} ({size / 2**20:.1f} MiB)")


if __name__ == "__main__":
    main()
