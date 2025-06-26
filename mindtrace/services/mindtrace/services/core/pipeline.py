class Pipeline:
    def __init__(self, name, input_schema=None, output_schema=None, func=None):
        self.name = name
        self.input_schema = input_schema
        self.output_schema = output_schema
        self.func = func

    def run(self, inputs):
        # Optionally validate inputs using input_schema
        if self.input_schema is not None:
            inputs = self.input_schema(**inputs)
        result = self.func(inputs)
        # Optionally validate outputs using output_schema
        if self.output_schema is not None:
            result = self.output_schema(**result) if isinstance(result, dict) else self.output_schema(result)
        return result 