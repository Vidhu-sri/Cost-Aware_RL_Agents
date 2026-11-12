import kagglehub

# Download latest version
path = kagglehub.dataset_download("metric/gemma-4-developer-agent-wheelhouse/versions/29")

print("Path to dataset files:", path)