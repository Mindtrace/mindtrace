import reflex as rx

from poseidon.components.stepper import StepConfig, stepper
import reflex as rx
from poseidon.state.neuroforge_create_line_state import (
    CreateLineState,
    CreateLineFlowState,
)

from poseidon.components_v2.forms.neuroforge_create_line_steps import (
    step_line_info,
    step_brain_selector,
    step_camera_config,
    step_data_capture_mapping,
    step_image_grid_label,
    step_model_training,
    step_deploy,
)

TOTAL_STEPS = 7

def neuroforge_create_line() -> rx.Component:
    cs = CreateLineFlowState.current_step
    is_loading = CreateLineFlowState.is_loading

    can_proceed = (
        ((cs == 1) & (True)) |
        ((cs == 2) & (CreateLineState.selected_brain != "")) |
        ((cs == 3) & (True)) |
        ((cs == 4) & (True)) |
        ((cs == 5) & ((CreateLineState.selected_images.length() > 0) & (CreateLineState.sent_to_label_studio))) |
        ((cs == 6) & (CreateLineState.training_status == "done")) |
        ((cs == 7) & (CreateLineState.training_status == "done"))
    )

    steps = [
        StepConfig(title="Line Info",     description="Name, plant and metadata",            completed=(cs > 1), content=step_line_info()),
        StepConfig(title="Brain Selector",         description="Pick the analysis brain",             completed=(cs > 2), content=step_brain_selector()),
        StepConfig(title="Camera Configurator",       description="Select & edit cameras",               completed=(cs > 3), content=step_camera_config()),
        StepConfig(title="Capture & Map", description="Map cameras & capture samples",       completed=(cs > 4), content=step_data_capture_mapping()),
        StepConfig(title="Data Curation",      description="Choose images to send to Label Studio", completed=(cs > 5), content=step_image_grid_label()),
        StepConfig(title="Training",      description="Select model and train with feedback", completed=(cs > 6), content=step_model_training()),
        StepConfig(title="Deploy",        description="Roll out the trained model",          completed=(cs > 7), content=step_deploy()),
    ]

    return rx.box(
        rx.vstack(
            stepper(
                steps=steps,
                current_step=cs,
                on_next=lambda: CreateLineFlowState.next(TOTAL_STEPS),
                on_previous=CreateLineFlowState.prev,
                on_finish=CreateLineFlowState.deploy_and_reset,
                can_proceed=can_proceed,
                is_loading=is_loading,
            ),
            spacing="6",
            width="100%",
            align="center",
            justify="center",
        ),
        min_height="100vh",
        display="flex",
        align_items="flex-start",
        justify_content="center",
    )
