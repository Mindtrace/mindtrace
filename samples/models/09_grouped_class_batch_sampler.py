"""Build grouped classification batches from a saved Hugging Face export."""

from pathlib import Path

from datasets import load_from_disk
from torchvision import transforms

from mindtrace.models.training import GroupedClassBatchSampler, build_dataloaders


EXPORT_PATH = Path("exports/grouped-classification")
SPLIT_NAME = "train"


def main() -> None:
    exported_dataset = load_from_disk(str(EXPORT_PATH))
    split = exported_dataset[SPLIT_NAME]

    # Callers define which typed fields together identify a logical group.
    group_ids = list(zip(split["subject_id"], split["session_id"], strict=True))

    batch_sampler = GroupedClassBatchSampler(
        labels=split["label"],
        group_ids=group_ids,
        classes_per_batch=4,
        samples_per_class=2,
        batches_per_epoch=10,
        seed=42,
    )

    transform = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
        ]
    )

    train_loader = build_dataloaders(
        EXPORT_PATH,
        task="classification",
        splits=(SPLIT_NAME,),
        transforms={SPLIT_NAME: transform},
        return_metadata=True,
        metadata_keys=("subject_id", "session_id"),
        per_split_dataloader_kwargs={
            SPLIT_NAME: {"batch_sampler": batch_sampler},
        },
    )[SPLIT_NAME]

    for epoch in range(2):
        # Change the sampling order deterministically at each epoch boundary.
        batch_sampler.set_epoch(epoch)

        for images, labels, metadata in train_loader:
            print(f"epoch={epoch}")
            print(f"image batch shape: {images.shape}")
            print(f"labels: {labels.tolist()}")
            print(f"first two metadata records: {metadata[:2]}")
            break


if __name__ == "__main__":
    main()
