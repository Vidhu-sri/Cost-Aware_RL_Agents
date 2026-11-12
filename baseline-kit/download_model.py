"""Use the exact Kaggle model instance/version mounted by the official starter."""
import json
from pathlib import Path
import kagglehub

handle = 'google/gemma-4/other/gemma-4-31b-it-qat-w4a16-ct/2'
root = Path(kagglehub.model_download(handle)).resolve()
config = json.loads((root / 'config.json').read_text())
quant = config.get('quantization_config', {})
groups = quant.get('config_groups', {})
assert any(g.get('weights', {}).get('num_bits') == 4 for g in groups.values()), quant
Path('model-path.txt').write_text(str(root) + '\n')
Path('model-source.json').write_text(json.dumps({'handle': handle, 'path': str(root), 'quantization_config': quant}, indent=2))
print('Exact starter model downloaded:', root)
