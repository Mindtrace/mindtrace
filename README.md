# Setup Instructions
## Install Required Packages

```
uv venv
uv pip install -e .[core]
```

## Test your installation

```
uv run python
from mindtrace.core import util
util.sum(2, 3)
```