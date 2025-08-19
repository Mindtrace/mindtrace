from typing import List

from pydantic import BaseModel, Field

from mindtrace.core import TaskSchema
from mindtrace.services import Service


class AddInput(BaseModel):
    """Arguments for adding a list of numbers."""

    numbers: List[float] = Field(..., description="Numbers to add")


class AddOutput(BaseModel):
    """Result of addition."""

    result: float


add_task = TaskSchema(name="add", input_schema=AddInput, output_schema=AddOutput)


class MultiplyInput(BaseModel):
    """Arguments for multiplying a list of numbers."""

    numbers: List[float] = Field(..., description="Numbers to multiply")


class MultiplyOutput(BaseModel):
    """Result of multiplication."""

    result: float


multiply_task = TaskSchema(name="multiply", input_schema=MultiplyInput, output_schema=MultiplyOutput)


class SubtractInput(BaseModel):
    """Arguments for subtraction of two numbers (a - b)."""

    a: float = Field(..., description="Minuend")
    b: float = Field(..., description="Subtrahend")


class SubtractOutput(BaseModel):
    """Result of subtraction."""

    result: float


subtract_task = TaskSchema(name="subtract", input_schema=SubtractInput, output_schema=SubtractOutput)


class DivideInput(BaseModel):
    """Arguments for division of two numbers (a / b)."""

    a: float = Field(..., description="Dividend")
    b: float = Field(..., description="Divisor (non-zero)")


class DivideOutput(BaseModel):
    """Result of division."""

    result: float


divide_task = TaskSchema(name="divide", input_schema=DivideInput, output_schema=DivideOutput)


class CalculatorService(Service):
    def __init__(self, *args, **kwargs):
        """Initialize a basic calculator service exposing simple math operations.

        The service registers four MCP tools: add, subtract, multiply, divide.
        """
        super().__init__(*args, **kwargs)

        self.add_endpoint("calc_add", self.calc_add, schema=add_task, as_tool=True)
        self.add_endpoint("calc_subtract", self.calc_subtract, schema=subtract_task, as_tool=True)
        self.add_endpoint("calc_multiply", self.calc_multiply, schema=multiply_task, as_tool=True)
        self.add_endpoint("calc_divide", self.calc_divide, schema=divide_task, as_tool=True)

    def calc_add(self, payload: AddInput) -> AddOutput:
        """Add all numbers in the list and return the sum."""
        if not payload.numbers:
            return AddOutput(result=0.0)
        total = float(sum(payload.numbers))
        return AddOutput(result=total)

    def calc_subtract(self, payload: SubtractInput) -> SubtractOutput:
        """Subtract b from a and return the result."""
        result_value = float(payload.a) - float(payload.b)
        return SubtractOutput(result=result_value)

    def calc_multiply(self, payload: MultiplyInput) -> MultiplyOutput:
        """Multiply all numbers in the list and return the product."""
        product = 1.0
        for value in payload.numbers:
            product *= float(value)
        return MultiplyOutput(result=product)

    def calc_divide(self, payload: DivideInput) -> DivideOutput:
        """Divide a by b and return the quotient."""
        if float(payload.b) == 0.0:
            raise ValueError("Division by zero is not allowed")
        quotient = float(payload.a) / float(payload.b)
        return DivideOutput(result=quotient)

