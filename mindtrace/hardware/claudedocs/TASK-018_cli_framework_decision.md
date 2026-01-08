# TASK-018: CLI Framework Decision - Typer

## Decision

**Typer** is the official CLI framework standard for all Mindtrace CLI tools.

## Background

The Hardware CLI was originally implemented using Click. This task migrates it to Typer for consistency with other Mindtrace CLI tools and to leverage Typer's modern features.

## Why Typer?

### 1. Type Hints Integration
Typer uses Python type hints for argument/option parsing, making code more readable and IDE-friendly:

```python
# Click
@click.option("--api-port", default=8002, type=int, help="API port")
def start(api_port):
    ...

# Typer
@app.command()
def start(
    api_port: Annotated[int, typer.Option("--api-port", help="API port")] = 8002,
):
    ...
```

### 2. Built-in Rich Integration
Typer automatically integrates with Rich for beautiful terminal output:
- Progress bars
- Colored output
- Tables
- Panels

### 3. Native Environment Variable Support
Typer supports environment variables directly in option definitions:

```python
api_host: Annotated[
    str, typer.Option("--api-host", envvar="CAMERA_API_HOST")
] = "localhost"
```

### 4. Modern Python Patterns
- Uses `Annotated` type hints (PEP 593)
- Supports async commands
- Better autocompletion generation

### 5. Consistent Ecosystem
All Mindtrace CLIs use Typer:
- `mindtrace-hw` - Hardware CLI
- `mindtrace-camera-setup` - Camera setup CLI
- `mindtrace-camera-basler` - Basler camera CLI
- `mindtrace-camera-genicam` - GenICam camera CLI
- `mindtrace-stereo-basler` - Stereo camera CLI

## Migration Summary

### Files Updated
- `cli/__main__.py` - Main CLI app
- `cli/commands/camera.py` - Camera commands
- `cli/commands/stereo.py` - Stereo camera commands
- `cli/commands/plc.py` - PLC commands
- `cli/commands/status.py` - Status command
- `cli/README.md` - Documentation

### Key Changes

1. **Click groups → Typer apps**
   ```python
   # Before
   @click.group()
   def camera():
       pass

   # After
   app = typer.Typer(help="Manage camera services")
   ```

2. **Click options → Annotated type hints**
   ```python
   # Before
   @click.option("--api-host", default="localhost")
   def start(api_host: str):
       pass

   # After
   @app.command()
   def start(
       api_host: Annotated[str, typer.Option("--api-host")] = "localhost",
   ):
       pass
   ```

3. **Click decorators → Typer decorators**
   - `@click.command()` → `@app.command()`
   - `@click.group()` → `typer.Typer()`
   - `click.echo()` → `typer.echo()`
   - `click.confirm()` → `typer.confirm()`

4. **Subcommand registration**
   ```python
   # Before
   app.add_command(camera)

   # After
   app.add_typer(camera_app, name="camera")
   ```

## Dependencies

Already in `pyproject.toml`:
```toml
dependencies = [
    "typer>=0.9.0",
    "rich>=13.0.0",
    ...
]
```

## References

- [Typer Documentation](https://typer.tiangolo.com/)
- [PEP 593 - Annotated](https://peps.python.org/pep-0593/)
- [Rich Documentation](https://rich.readthedocs.io/)
