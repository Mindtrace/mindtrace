"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import {
  listModels,
  createModel,
  updateModel,
  getSafeErrorMessage,
  isSessionOrAuthError,
} from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Model } from "@/lib/api/types";
import { LoadingOverlay } from "@/components/ui/loading-overlay";
import { ModelsPagination } from "./models-pagination";
import { ModelsTable } from "./models-table";

const PAGE_SIZE = 10;

export function ModelsPanel() {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createVersion, setCreateVersion] = useState("");
  const [editing, setEditing] = useState<Model | null>(null);
  const [editName, setEditName] = useState("");
  const [editVersion, setEditVersion] = useState("");
  const [page, setPage] = useState(1);

  const dialogOpen = showCreate || editing !== null;

  const { data, isLoading, error } = useQuery({
    queryKey: ["models", page],
    queryFn: () =>
      listModels({
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
      }),
  });

  const createMutation = useMutation({
    mutationFn: (payload: { name: string; version: string }) =>
      createModel(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["models"] });
      setCreateName("");
      setCreateVersion("");
      toast.success("Model created successfully.");
      setShowCreate(false);
    },
    onError: (err: Error) => {
      if (!isSessionOrAuthError(err))
        toast.error(getSafeErrorMessage(err, "Failed to add model."));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      name,
      version,
    }: {
      id: string;
      name?: string;
      version?: string;
    }) => updateModel(id, { name, version }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["models"] });
      toast.success("Model updated successfully.");
      setEditing(null);
    },
    onError: (err: Error) => {
      if (!isSessionOrAuthError(err))
        toast.error(getSafeErrorMessage(err, "Failed to update model."));
    },
  });

  function closeDialog() {
    setShowCreate(false);
    setEditing(null);
  }

  function startEdit(model: Model) {
    setEditing(model);
    setEditName(model.name);
    setEditVersion(model.version ?? "");
  }

  if (isLoading) return <LoadingOverlay />;
  if (error) {
    return (
      <Card>
        <CardContent className="pt-6">
          <p className="text-destructive">
            {getSafeErrorMessage(error, "Something went wrong.")}
          </p>
        </CardContent>
      </Card>
    );
  }

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-6">
      <Dialog open={dialogOpen} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editing ? "Edit model" : "Add model"}</DialogTitle>
          </DialogHeader>
          {editing ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const name = editName.trim() || undefined;
                const version = editVersion.trim() || undefined;
                if (name === undefined && version === undefined) return;
                updateMutation.mutate({ id: editing.id, name, version });
              }}
              className="space-y-4"
            >
              {updateMutation.isError &&
                !isSessionOrAuthError(updateMutation.error) && (
                  <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                    {getSafeErrorMessage(
                      updateMutation.error,
                      "Failed to update model."
                    )}
                  </p>
                )}
              <div className="space-y-2">
                <Label htmlFor="edit-model-name">Name</Label>
                <Input
                  id="edit-model-name"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  placeholder="Model name"
                  disabled={updateMutation.isPending}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-model-version">Version</Label>
                <Input
                  id="edit-model-version"
                  value={editVersion}
                  onChange={(e) => setEditVersion(e.target.value)}
                  placeholder="e.g. 1.0.0"
                  disabled={updateMutation.isPending}
                />
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={closeDialog}>
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={
                    (!editName.trim() && !editVersion.trim()) ||
                    updateMutation.isPending
                  }
                >
                  {updateMutation.isPending ? "Saving…" : "Save"}
                </Button>
              </DialogFooter>
            </form>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const name = createName.trim();
                const version = createVersion.trim();
                if (!name || !version) return;
                createMutation.mutate({ name, version });
              }}
              className="space-y-4"
            >
              {createMutation.isError &&
                !isSessionOrAuthError(createMutation.error) && (
                  <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                    {getSafeErrorMessage(
                      createMutation.error,
                      "Failed to add model."
                    )}
                  </p>
                )}
              <div className="space-y-2">
                <Label htmlFor="create-model-name">Name</Label>
                <Input
                  id="create-model-name"
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  placeholder="Model name"
                  disabled={createMutation.isPending}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="create-model-version">Version</Label>
                <Input
                  id="create-model-version"
                  value={createVersion}
                  onChange={(e) => setCreateVersion(e.target.value)}
                  placeholder="e.g. 1.0.0"
                  disabled={createMutation.isPending}
                />
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={closeDialog}>
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={
                    !createName.trim() ||
                    !createVersion.trim() ||
                    createMutation.isPending
                  }
                >
                  {createMutation.isPending ? "Creating…" : "Create"}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4 py-4">
          <div className="flex items-center gap-2" />
          <Button onClick={() => setShowCreate(true)}>Add model</Button>
        </CardHeader>
        <CardContent>
          {items.length === 0 ? (
            <p className="py-8 text-center text-muted-foreground">
              No models yet.
            </p>
          ) : (
            <>
              <ModelsTable items={items} onEdit={startEdit} />
              <ModelsPagination
                page={page}
                totalPages={totalPages}
                total={total}
                pageSize={PAGE_SIZE}
                onPageChange={setPage}
              />
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
