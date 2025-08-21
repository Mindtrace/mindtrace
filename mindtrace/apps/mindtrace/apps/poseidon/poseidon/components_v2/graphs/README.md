# Graphs Components

Beautiful, responsive chart components that follow the Poseidon design system. This package includes pie charts, line charts, and bar charts with consistent styling and interactive features.

## Components Overview

- **Pie Chart**: Circular charts for showing proportions and percentages
- **Line Chart**: Trend visualization with support for multiple series
- **Bar Chart**: Categorical data visualization with horizontal/vertical layouts

## Common Features

All chart components share these features:

- **Design System Integration**: Follows Poseidon's color scheme and styling
- **Responsive**: Adapts to different screen sizes
- **Customizable**: Multiple configuration options
- **Animated**: Smooth animations and hover effects
- **Interactive**: Hover tooltips and click events
- **Card Variants**: Optional card wrapper with different styles

## Color Scheme

All charts automatically use Poseidon's color palette:

- Primary Blue: `#0057FF`
- Secondary Sky Blue: `#0EA5E9`
- Success Green: `#10B981`
- Warning Amber: `#F59E0B`
- Error Red: `#EF4444`
- Purple: `#8B5CF6`
- Cyan: `#06B6D4`
- Lime: `#84CC16`
- Orange: `#F97316`
- Pink: `#EC4899`
- Indigo: `#6366F1`
- Teal: `#14B8A6`

Colors are automatically assigned to data points and will cycle if you have more than 12 categories.

## Pie Chart Component

The pie chart component provides a beautiful, customizable pie chart with support for various configurations including doughnut charts, half-pie charts, and interactive cards.

### Basic Usage

```python
from poseidon.components_v2.graphs import pie_chart, pie_chart_card

# Sample data
data = [
    {"name": "Revenue", "value": 400},
    {"name": "Expenses", "value": 300},
    {"name": "Profit", "value": 200},
]

# Basic pie chart
chart = pie_chart(
    data=data,
    title="Financial Overview",
    subtitle="Q4 2024 Performance",
    height=300,
)
```

### Advanced Usage

```python
# Interactive card chart
card_chart = pie_chart_card(
    data=data,
    title="Sales Distribution",
    subtitle="Revenue by Category",
    height=350,
    show_labels=True,
    show_legend=True,
    show_tooltip=True,
    inner_radius="30%",  # Creates a doughnut chart
    padding_angle=3,     # Space between slices
    card_variant="interactive",  # Adds hover effects
)
```

### Pie Chart Configuration

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `data` | `List[Dict[str, Any]]` | Required | Data array with name and value keys |
| `data_key` | `str` | `"value"` | Key for numerical values in data |
| `name_key` | `str` | `"name"` | Key for category names in data |
| `title` | `Optional[str]` | `None` | Chart title |
| `subtitle` | `Optional[str]` | `None` | Chart subtitle |
| `width` | `Union[str, int]` | `"100%"` | Chart width |
| `height` | `Union[str, int]` | `300` | Chart height |
| `show_labels` | `bool` | `True` | Show labels on pie slices |
| `show_legend` | `bool` | `True` | Show legend below chart |
| `show_tooltip` | `bool` | `True` | Show tooltip on hover |
| `inner_radius` | `Union[str, int]` | `"0%"` | Inner radius (0% = full pie, >0% = doughnut) |
| `outer_radius` | `Union[str, int]` | `"80%"` | Outer radius of the chart |
| `padding_angle` | `int` | `2` | Space between pie slices in degrees |
| `start_angle` | `int` | `0` | Starting angle in degrees |
| `end_angle` | `int` | `360` | Ending angle in degrees |
| `animate` | `bool` | `True` | Enable animations |

### Pie Chart Examples

#### Basic Pie Chart
```python
pie_chart(
    data=data,
    title="Simple Pie Chart",
    height=300,
)
```

#### Doughnut Chart
```python
pie_chart(
    data=data,
    title="Doughnut Chart",
    inner_radius="60%",
    outer_radius="90%",
    padding_angle=5,
    height=300,
)
```

#### Half Pie Chart
```python
pie_chart(
    data=data,
    title="Half Pie Chart",
    start_angle=180,
    end_angle=0,
    inner_radius="40%",
    height=300,
)
```

## Line Chart Component

The line chart component provides trend visualization with support for single and multiple data series, smooth curves, and interactive features.

### Basic Usage

```python
from poseidon.components_v2.graphs import line_chart, line_chart_card

# Sample data
data = [
    {"month": "Jan", "sales": 400},
    {"month": "Feb", "sales": 300},
    {"month": "Mar", "sales": 600},
]

# Basic line chart
chart = line_chart(
    data=data,
    x_key="month",
    y_key="sales",
    title="Monthly Sales",
    height=300,
)
```

### Advanced Usage

```python
# Multi-series line chart
data = [
    {"month": "Jan", "sales": 400, "revenue": 2400},
    {"month": "Feb", "sales": 300, "revenue": 1398},
    {"month": "Mar", "sales": 600, "revenue": 9800},
]

card_chart = line_chart_card(
    data=data,
    x_key="month",
    y_key="sales",
    y_keys=["sales", "revenue"],  # Multiple series
    title="Sales vs Revenue Trends",
    subtitle="Multi-series comparison",
    height=350,
    show_grid=True,
    show_legend=True,
    smooth=True,  # Smooth curves
    card_variant="interactive",
)
```

### Line Chart Configuration

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `data` | `List[Dict[str, Any]]` | Required | Data array |
| `x_key` | `str` | `"x"` | Key for x-axis values |
| `y_key` | `str` | `"y"` | Key for y-axis values (single series) |
| `y_keys` | `Optional[List[str]]` | `None` | Keys for multiple y-axis series |
| `series_key` | `Optional[str]` | `None` | Key for grouping data into series |
| `title` | `Optional[str]` | `None` | Chart title |
| `subtitle` | `Optional[str]` | `None` | Chart subtitle |
| `width` | `Union[str, int]` | `"100%"` | Chart width |
| `height` | `Union[str, int]` | `300` | Chart height |
| `show_grid` | `bool` | `True` | Show grid lines |
| `show_legend` | `bool` | `True` | Show legend |
| `show_tooltip` | `bool` | `True` | Show tooltip on hover |
| `show_dots` | `bool` | `True` | Show data points |
| `smooth` | `bool` | `False` | Use smooth curves |
| `animate` | `bool` | `True` | Enable animations |

### Line Chart Examples

#### Single Series
```python
line_chart(
    data=data,
    x_key="month",
    y_key="sales",
    title="Monthly Sales",
    height=300,
)
```

#### Multiple Series
```python
line_chart(
    data=data,
    x_key="month",
    y_key="sales",
    y_keys=["sales", "revenue"],
    title="Sales vs Revenue",
    height=300,
    smooth=True,
)
```

## Bar Chart Component

The bar chart component provides categorical data visualization with support for horizontal/vertical layouts, multiple series, and custom styling.

### Basic Usage

```python
from poseidon.components_v2.graphs import bar_chart, bar_chart_card

# Sample data
data = [
    {"category": "Feature A", "value": 400},
    {"category": "Feature B", "value": 300},
    {"category": "Feature C", "value": 600},
]

# Basic bar chart
chart = bar_chart(
    data=data,
    x_key="category",
    y_key="value",
    title="Feature Usage",
    height=300,
)
```

### Advanced Usage

```python
# Multi-series bar chart
data = [
    {"day": "Mon", "defects": 12, "resolved": 8},
    {"day": "Tue", "defects": 15, "resolved": 10},
    {"day": "Wed", "defects": 8, "resolved": 12},
]

card_chart = bar_chart_card(
    title="Defect Trends",
    subtitle="Defects found vs resolved per day",
    children=bar_chart(
        data=data,
        x_key="day",
        y_key="defects",
        y_keys=["defects", "resolved"],  # Multiple series
        height=350,
        show_grid=True,
        show_legend=True,
        bar_gap=8,
        bar_category_gap="15%",
    ),
    card_variant="interactive",
)
```

### Bar Chart Configuration

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `data` | `List[Dict[str, Any]]` | Required | Data array |
| `x_key` | `str` | `"x"` | Key for x-axis values |
| `y_key` | `str` | `"y"` | Key for y-axis values (single series) |
| `y_keys` | `Optional[List[str]]` | `None` | Keys for multiple y-axis series |
| `title` | `Optional[str]` | `None` | Chart title |
| `subtitle` | `Optional[str]` | `None` | Chart subtitle |
| `width` | `Union[str, int]` | `"100%"` | Chart width |
| `height` | `Union[str, int]` | `300` | Chart height |
| `show_grid` | `bool` | `True` | Show grid lines |
| `show_legend` | `bool` | `True` | Show legend |
| `show_tooltip` | `bool` | `True` | Show tooltip on hover |
| `layout` | `str` | `"horizontal"` | Chart layout ("horizontal" or "vertical") |
| `bar_size` | `Optional[int]` | `None` | Size of bars in pixels |
| `bar_gap` | `Union[str, int]` | `4` | Gap between bars in same category |
| `bar_category_gap` | `Union[str, int]` | `"10%"` | Gap between bar categories |
| `animate` | `bool` | `True` | Enable animations |

### Bar Chart Card Configuration

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `title` | `str` | Required | Card title |
| `subtitle` | `Optional[str]` | `None` | Card subtitle |
| `children` | `Optional[rx.Component]` | `None` | The component to wrap in the card (e.g., a chart) |
| `card_variant` | `str` | `"default"` | Card styling variant |

### Bar Chart Examples

#### Horizontal Bar Chart
```python
bar_chart(
    data=data,
    x_key="category",
    y_key="value",
    title="Feature Usage",
    height=300,
)
```

#### Vertical Bar Chart
```python
bar_chart(
    data=data,
    x_key="category",
    y_key="value",
    title="Feature Usage",
    layout="vertical",
    height=300,
)
```

#### Multiple Series
```python
bar_chart(
    data=data,
    x_key="day",
    y_key="defects",
    y_keys=["defects", "resolved"],
    title="Defect Trends",
    height=300,
    bar_gap=8,
)
```

## Card Variants

All chart components support card variants:

- `"default"`: Standard card styling
- `"interactive"`: Adds hover effects and animations

### Card Example

```python
# All components support card variants
pie_chart_card(data=data, title="Pie Chart", card_variant="interactive")
line_chart_card(data=data, title="Line Chart", card_variant="interactive")
bar_chart_card(
    title="Bar Chart", 
    children=bar_chart(data=data, x_key="x", y_key="y"),
    card_variant="interactive"
)
```

## Data Format

### Pie Chart Data
```python
data = [
    {"name": "Category Name", "value": 100},
    {"name": "Another Category", "value": 200},
    # ... more data points
]
```

### Line/Bar Chart Data
```python
# Single series
data = [
    {"x": "Category A", "y": 100},
    {"x": "Category B", "y": 200},
    # ... more data points
]

# Multiple series
data = [
    {"x": "Category A", "series1": 100, "series2": 150},
    {"x": "Category B", "series1": 200, "series2": 250},
    # ... more data points
]
```

## Styling Integration

All chart components integrate seamlessly with Poseidon's design system:

- Uses the app's typography system
- Follows the color palette
- Applies consistent spacing and sizing
- Includes backdrop blur effects
- Supports the app's shadow system
- Uses the same border radius and transitions

## Demo

See `demo.py` for comprehensive examples of all chart configurations and use cases, including:

- Simple and advanced examples for each chart type
- Defect trends visualization with bar charts
- Multi-series line charts
- Interactive card variants
- Various styling configurations

## Installation

The chart components are part of the Poseidon design system and are automatically available when you import from the graphs module:

```python
from poseidon.components_v2.graphs import (
    pie_chart, pie_chart_card,
    line_chart, line_chart_card,
    bar_chart, bar_chart_card
)
```