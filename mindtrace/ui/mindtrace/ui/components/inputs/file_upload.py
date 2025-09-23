import reflex as rx
from typing import Optional


class _UploadState(rx.State):
    """
    Per-`cid` store for uploaded file names and async upload handler.

    Attributes:
        uploaded (dict[str, list[str]]): Mapping of uploader IDs (`cid`) to lists of
            uploaded file names.
    """
    uploaded: dict[str, list[str]] = {}

    @rx.event
    async def handle_upload(self, files: list[rx.UploadFile], cid: str) -> None:
        """
        Save selected files to the upload directory and record their names for `cid`.

        Args:
            files (list[rx.UploadFile]): Files selected via `rx.upload_files(cid)`.
            cid (str): Uploader identifier used to group uploaded files.
        """
        new_names: list[str] = []
        for f in files:
            data = await f.read()
            path = rx.get_upload_dir() / f.name
            with path.open("wb") as out:
                out.write(data)
            new_names.append(f.name)

        current = list(self.uploaded.get(cid, []))
        current.extend(new_names)
        self.uploaded[cid] = current

    def clear_selected(self, cid: str):
        """
        Clear only the client-side selection for this uploader.

        Note:
            This does not affect files already uploaded or saved to disk.
        """
        return rx.clear_selected_files(cid)

    def clear_uploaded(self, cid: str) -> None:
        """
        Clear the uploaded list in state for `cid`.

        Note:
            This does not delete files from disk.
        """
        self.uploaded[cid] = []


def file_uploader(
    cid: str = "upload1",
    accept: str = "",
    multiple: bool = True,
    button_label: str = "Choose files",
) -> rx.Component:
    """
    Render a minimal, state-driven file uploader.

    Uses `rx.upload(id=cid)` for selection/drag-drop. The **Upload** button
    triggers `_UploadState.handle_upload(rx.upload_files(cid), cid)`. Below the
    dropzone it shows both the currently selected files (pre-upload) and the
    uploaded files (post-upload) for the same `cid`.

    Args:
        cid (str, optional): Uploader identifier shared across controls. Defaults to "upload1".
        accept (str, optional): Comma-separated list of accepted MIME types or extensions. Defaults to "" (any).
        multiple (bool, optional): Allow multiple file selection. Defaults to True.
        button_label (str, optional): Label for the file picker button. Defaults to "Choose files".

    Returns:
        rx.Component: A vertical stack containing the dropzone, actions, and file lists.
    """
    return rx.vstack(
        rx.upload(
            rx.vstack(
                rx.icon(tag="upload"),
                rx.text("Drop files here or"),
                rx.button(button_label, type="button", variant="outline"),
                spacing="2",
                align="center",
            ),
            id=cid,
            accept=accept,
            multiple=multiple,
            width="100%",
            padding="1rem",
            border="1px dashed #cbd5e1",
            border_radius="10px",
            background="#ffffff",
            _hover={"background": "#f8fafc"},
        ),

        rx.hstack(
            rx.button(
                "Upload",
                on_click=_UploadState.handle_upload(
                    rx.upload_files(cid),
                    cid,
                ),
            ),
            rx.button(
                "Clear selection",
                variant="ghost",
                on_click=lambda: _UploadState.clear_selected(cid),
            ),
            rx.button(
                "Clear uploaded",
                variant="ghost",
                on_click=lambda: _UploadState.clear_uploaded(cid),
            ),
            spacing="2",
        ),

        rx.vstack(
            rx.hstack(rx.icon(tag="file"), rx.text("Selected"), spacing="2", align="center"),
            rx.cond(
                rx.selected_files(cid).length() > 0,
                rx.vstack(
                    rx.foreach(
                        rx.selected_files(cid),
                        lambda f: rx.text(f),
                    ),
                    spacing="1",
                    align="start",
                    width="100%",
                ),
                rx.text("None", color="#94a3b8"),
            ),
            spacing="2",
            width="100%",
        ),

        rx.vstack(
            rx.hstack(rx.icon(tag="image"), rx.text("Uploaded"), spacing="2", align="center"),
            rx.cond(
                _UploadState.uploaded.get(cid, []).length() > 0,
                rx.vstack(
                    rx.foreach(
                        _UploadState.uploaded.get(cid, []),
                        lambda name: rx.hstack(
                            rx.image(src=rx.get_upload_url(name), height="60px", width="auto"),
                            rx.text(name, size="2"),
                            spacing="2",
                            align="center",
                        ),
                    ),
                    spacing="2",
                    align="start",
                    width="100%",
                ),
                rx.text("None", color="#94a3b8"),
            ),
            spacing="2",
            width="100%",
        ),

        spacing="3",
        width="100%",
    )
