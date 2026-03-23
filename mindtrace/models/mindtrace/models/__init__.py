from mindtrace.models.pipeline import (
    Pipeline,
    PipelineLoadedOutput,
    PipelineLoadedTaskSchema,
    PipelineLoadInput,
    PipelineLoadOutput,
    PipelineLoadTaskSchema,
    PipelineUnloadInput,
    PipelineUnloadOutput,
    PipelineUnloadTaskSchema,
)

__all__ = [
    "AutoSegmenter",
    "AutoSegmenterInput",
    "AutoSegmenterOutput",
    "AutoSegmenterTaskSchema",
    "BoundingBoxPrediction",
    "Pipeline",
    "PipelineLoadInput",
    "PipelineLoadOutput",
    "PipelineLoadTaskSchema",
    "PipelineLoadedOutput",
    "PipelineLoadedTaskSchema",
    "PipelineUnloadInput",
    "PipelineUnloadOutput",
    "PipelineUnloadTaskSchema",
    "SegmentationMaskPrediction",
]

_AUTO_SEGMENTER_NAMES = frozenset(
    {
        "AutoSegmenter",
        "AutoSegmenterInput",
        "AutoSegmenterOutput",
        "AutoSegmenterTaskSchema",
        "BoundingBoxPrediction",
        "SegmentationMaskPrediction",
    }
)


def __getattr__(name):
    if name in _AUTO_SEGMENTER_NAMES:
        from mindtrace.models import auto_segmenter as _mod

        for _n in _AUTO_SEGMENTER_NAMES:
            globals()[_n] = getattr(_mod, _n)
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
