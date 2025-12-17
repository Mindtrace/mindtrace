# mindtrace/agents/composer/composer.py

from strands import Agent


class AgentComposer:
    """
    AgentComposer that creates a Mindtrace Agent
    from a model, system prompt, and tools.
    """

    def __init__(self, model=None, system_prompt=None, tools=None, **kwargs):
        self.model = model
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.kwargs = kwargs

    def compose_strands_agent(self):
        """
        Returns a Strands Agent instantiated with the provided
        model, system prompt, tools and any extra kwargs.
        """
        return Agent(model=self.model, system_prompt=self.system_prompt, tools=self.tools, **self.kwargs)


def get_agent(model=None, system_prompt=None, tools=None, **kwargs):
    """
    Factory function to create a Strands Agent.
    """
    composer = AgentComposer(model=model, system_prompt=system_prompt, tools=tools, **kwargs)
    return composer.compose_strands_agent()
