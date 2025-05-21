# Setup Instructions
## Install Required Packages

```
uv venv
uv pip install -e .[services]
```

## Test your installation

```
uv run python
from mindtrace.core import util
util.sum(2, 3)
from mindtrace.services import util
util.subtract(5, 3)
```