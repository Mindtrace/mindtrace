from typing import TYPE_CHECKING, Any, Dict

# No longer importing Pydantic models - working with dicts directly

if TYPE_CHECKING:
    pass


def resolve_provider_config(provider_key: str, providers: Dict[str, Any]) -> dict:
    if provider_key not in providers:
        raise KeyError(
            f"Provider '{provider_key}' not found in providers. Available providers: {list(providers.keys())}"
        )

    provider_data = providers[provider_key]

    return provider_data


def get_ollama_model(model_id: str, **kwargs):
    """Get an Ollama model instance.

    Args:
        model_id: The model identifier (e.g., "llama3", "mistral").
        **kwargs: Additional keyword arguments to pass to OllamaModel.
            Common kwargs include:
            - host: The base URL for the Ollama API (defaults to "http://localhost:11434").
            - timeout: Request timeout in seconds.

    Returns:
        An OllamaModel instance configured with the specified model_id and kwargs.

    Raises:
        ImportError: If the ollama package is not installed.
    """
    try:
        from strands.models.ollama import OllamaModel
    except ImportError as e:
        raise ImportError(
            f"Ollama model requires the 'ollama' package to be installed. {e} Install it with: pip install ollama"
        ) from e

    return OllamaModel(model_id=model_id, **kwargs)


def get_openai_model(model_id: str, api_key: str = None, **kwargs):
    """Get an OpenAI model instance.

    Args:
        model_id: The model identifier (e.g., "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo").
        api_key: OpenAI API key. If not provided, will try to get from environment variable
                 or provider config.
        **kwargs: Additional keyword arguments to pass to OpenAIModel.
            Common kwargs include:
            - base_url: Custom base URL for OpenAI-compatible API (optional).
            - params: Dict with model parameters like max_tokens, temperature, etc.
            - client_args: Dict with additional client arguments.

    Returns:
        An OpenAIModel instance configured with the specified model_id and kwargs.

    Raises:
        ImportError: If the openai package is not installed.
        ValueError: If api_key is not provided and not found in environment.

    Example:
        ```python
        model = get_openai_model(
            model_id="gpt-4o",
            api_key="sk-...",
            params={"max_tokens": 1000, "temperature": 0.7}
        )
        ```
    """
    try:
        from strands.models.openai import OpenAIModel
    except ImportError as e:
        raise ImportError(
            f"OpenAI model requires the 'openai' package to be installed. {e} Install it with: pip install openai"
        ) from e

    return OpenAIModel(
        model_id=model_id,
        client_args={
            "api_key": api_key,
        },
        params={
            "max_tokens": 1000,
            "temperature": 0.7,
        },
    )


def get_model_from_provider(provider_config: dict, model_name: str, **kwargs) -> Any:
    """Get a model instance from a provider configuration.

    Args:
        provider_config: Dictionary containing the provider configuration.
            This should be resolved from MT_LLM_PROVIDERS using the provider key.
        model_name: The name/ID of the model to use.
        **kwargs: Additional keyword arguments to pass to the model constructor.
            These will override any defaults from the provider config.

    Returns:
        A model instance configured according to the provider.

    Example:
        ```python
        from mindtrace.agents.core.providers import get_model_from_provider

        provider = {
            "type": "ollama",
            "base_url": "http://localhost:11434",
            "default_model": "llama3"
        }

        model = get_model_from_provider(
            provider_config=provider,
            model_name="llama3"
        )
        ```
    """
    provider_type = provider_config.get("type")

    match provider_type:
        case "ollama":
            model_kwargs = {"host": provider_config.get("base_url", "http://localhost:11434"), **kwargs}
            return get_ollama_model(model_id=model_name, **model_kwargs)

        case "openai":
            # Get API key from config or environment
            api_key = provider_config.get("api_key")

            return get_openai_model(model_id=model_name, api_key=api_key, **kwargs)

        case _:
            raise ValueError(f"Unsupported provider type: {provider_type}")
