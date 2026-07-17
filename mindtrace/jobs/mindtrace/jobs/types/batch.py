from dataclasses import dataclass, field


@dataclass
class BatchPublishResult:
    """Outcome of publishing an ordered batch of jobs.

    ``job_ids`` has one entry per input job. Failed and unattempted jobs have
    a value of ``None``. ``errors`` contains details for jobs whose publish was
    attempted and failed; later jobs left unattempted after a failure are not
    included in ``errors``.
    """

    job_ids: list[str | None]
    errors: dict[int, dict[str, str]] = field(default_factory=dict)

    @classmethod
    def for_batch_size(cls, size: int) -> "BatchPublishResult":
        """Create an empty result for a batch containing ``size`` jobs."""
        return cls(job_ids=[None] * size)

    @property
    def successful_indices(self) -> list[int]:
        """Indices of jobs published successfully."""
        return [index for index, job_id in enumerate(self.job_ids) if job_id is not None]

    @property
    def failed_indices(self) -> list[int]:
        """Indices of jobs whose publish was attempted and failed."""
        return list(self.errors)

    @property
    def unattempted_indices(self) -> list[int]:
        """Indices not attempted because an earlier publish failed."""
        return [index for index, job_id in enumerate(self.job_ids) if job_id is None and index not in self.errors]

    @property
    def success_count(self) -> int:
        return len(self.successful_indices)

    @property
    def failure_count(self) -> int:
        return len(self.failed_indices)

    @property
    def unattempted_count(self) -> int:
        return len(self.unattempted_indices)

    @property
    def all_succeeded(self) -> bool:
        return self.failure_count == 0 and self.unattempted_count == 0
