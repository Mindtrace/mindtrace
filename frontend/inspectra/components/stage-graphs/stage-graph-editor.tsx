"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { createStage, getSafeErrorMessage, listStages } from "@/lib/api/client";
import {
  getStageGraph,
  updateStageGraphStages,
  type StageGraphStageItem,
} from "@/lib/api/stage-graphs";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
import { LoadingOverlay } from "@/components/ui/loading-overlay";
import { ChevronDown } from "lucide-react";

export function StageGraphEditor({ id }: { id: string }) {
  const queryClient = useQueryClient();
  const [newStageName, setNewStageName] = useState("");
  const [selectedStageId, setSelectedStageId] = useState("");
  const [addingOrder, setAddingOrder] = useState(0);
  const [addingLabel, setAddingLabel] = useState("");
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editOrder, setEditOrder] = useState(0);
  const [editLabel, setEditLabel] = useState("");

  const {
    data: graph,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["stage-graphs", id],
    queryFn: () => getStageGraph(id),
  });

  const { data: stagesData } = useQuery({
    queryKey: ["stages"],
    queryFn: () => listStages({ limit: 500 }),
  });
  const stageNameSetLower = useMemo(() => {
    const items = stagesData?.items ?? [];
    return new Set(items.map((s) => s.name.trim().toLowerCase()));
  }, [stagesData]);
  const stageNameById = useMemo(() => {
    const items = stagesData?.items ?? [];
    return new Map(items.map((s) => [s.id, s.name] as const));
  }, [stagesData]);

  const ordered = useMemo(() => {
    const items = (graph?.stages ?? []).slice();
    items.sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
    return items;
  }, [graph]);

  const maxOrder = useMemo(() => {
    return (graph?.stages ?? []).reduce((m, x) => Math.max(m, x.order ?? 0), 0);
  }, [graph]);

  const updateMutation = useMutation({
    mutationFn: async (payload: { stages: StageGraphStageItem[] }) =>
      updateStageGraphStages(id, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["stage-graphs", id] });
      await queryClient.invalidateQueries({ queryKey: ["stage-graphs"] });
      toast.success("Stage graph updated.");
    },
    onError: (e: Error) => {
      toast.error(getSafeErrorMessage(e, "Failed to update stage graph."));
    },
  });

  const createStageMutation = useMutation({
    mutationFn: async (name: string) => createStage({ name }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["stages"] });
    },
  });

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

  const currentStages: StageGraphStageItem[] = (graph?.stages ?? []).map(
    (s) => ({
      stage_id: s.stage_id,
      order: s.order,
      label: s.label,
    })
  );

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="py-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate text-lg font-semibold">{graph?.name}</p>
              <p className="font-mono text-xs text-muted-foreground">{id}</p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                queryClient.invalidateQueries({
                  queryKey: ["stage-graphs", id],
                })
              }
            >
              Refresh
            </Button>
          </div>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader className="py-4">
          <p className="font-medium">Stages</p>
          <p className="text-sm text-muted-foreground">
            Order controls sequence. Stages with the same order run in parallel.
          </p>
        </CardHeader>
        <CardContent className="space-y-3">
          {ordered.length === 0 ? (
            <p className="text-sm text-muted-foreground">No stages yet.</p>
          ) : (
            <div className="space-y-2">
              {ordered.map((s, idx) => (
                <div
                  key={`${s.stage_id}-${idx}`}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium">
                      {s.stage_name ?? stageNameById.get(s.stage_id) ?? "Stage"}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      order: <span className="font-mono">{s.order}</span>
                      {s.label ? (
                        <>
                          {" "}
                          · label: <span className="font-mono">{s.label}</span>
                        </>
                      ) : null}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={updateMutation.isPending}
                      onClick={() => {
                        setEditingIndex(idx);
                        setEditOrder(Number(s.order ?? 0));
                        setEditLabel(s.label ?? "");
                      }}
                    >
                      Edit
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-destructive"
                      disabled={updateMutation.isPending}
                      onClick={() => {
                        const next = ordered.filter((_, j) => j !== idx);
                        updateMutation.mutate({
                          stages: next.map((x) => ({
                            stage_id: x.stage_id,
                            order: x.order,
                            label: x.label,
                          })),
                        });
                      }}
                    >
                      Remove
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <Dialog
            open={editingIndex !== null}
            onOpenChange={(open) => {
              if (!open) setEditingIndex(null);
            }}
          >
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle>Edit stage entry</DialogTitle>
                <DialogDescription>
                  Same order means parallel capture.
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="sg-edit-order">Order</Label>
                  <Input
                    id="sg-edit-order"
                    type="number"
                    min={0}
                    value={editOrder}
                    onChange={(e) =>
                      setEditOrder(
                        Math.max(
                          0,
                          Number.parseInt(e.target.value || "0", 10) || 0
                        )
                      )
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="sg-edit-label">Label (optional)</Label>
                  <Input
                    id="sg-edit-label"
                    value={editLabel}
                    onChange={(e) => setEditLabel(e.target.value)}
                    placeholder="e.g. left"
                  />
                </div>
              </div>
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setEditingIndex(null)}
                  disabled={updateMutation.isPending}
                >
                  Cancel
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={updateMutation.isPending || editingIndex === null}
                  onClick={() => {
                    if (editingIndex === null) return;
                    const next = ordered.slice();
                    const target = next[editingIndex];
                    next[editingIndex] = {
                      ...target,
                      order: editOrder,
                      label: editLabel.trim() || undefined,
                    };
                    updateMutation.mutate({
                      stages: next.map((x) => ({
                        stage_id: x.stage_id,
                        order: x.order,
                        label: x.label,
                      })),
                    });
                    setEditingIndex(null);
                  }}
                >
                  Save
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          <div className="grid gap-3 rounded-md border bg-card p-3 sm:grid-cols-4">
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="sg-stage-select">Stage</Label>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    id="sg-stage-select"
                    variant="outline"
                    className="w-full justify-between"
                    type="button"
                  >
                    <span className="truncate">
                      {selectedStageId
                        ? (stageNameById.get(selectedStageId) ?? "Stage")
                        : "Create new…"}
                    </span>
                    <ChevronDown className="ml-2 h-4 w-4 opacity-50" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  align="start"
                  className="w-[var(--radix-dropdown-menu-trigger-width)]"
                >
                  <DropdownMenuItem
                    onClick={() => {
                      setSelectedStageId("");
                    }}
                  >
                    Create new…
                  </DropdownMenuItem>
                  {(stagesData?.items ?? []).map((s) => (
                    <DropdownMenuItem
                      key={s.id}
                      onClick={() => {
                        setSelectedStageId(s.id);
                        setNewStageName("");
                      }}
                    >
                      {s.name}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>

              {selectedStageId ? null : (
                <div className="space-y-2">
                  <Label htmlFor="sg-new-stage">New stage name</Label>
                  <Input
                    id="sg-new-stage"
                    value={newStageName}
                    onChange={(e) => setNewStageName(e.target.value)}
                    placeholder="e.g. stage-a"
                  />
                </div>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="sg-new-order">Order</Label>
              <Input
                id="sg-new-order"
                type="number"
                min={0}
                value={addingOrder}
                onChange={(e) =>
                  setAddingOrder(
                    Math.max(0, Number.parseInt(e.target.value || "0", 10) || 0)
                  )
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="sg-new-label">Label (optional)</Label>
              <Input
                id="sg-new-label"
                value={addingLabel}
                onChange={(e) => setAddingLabel(e.target.value)}
                placeholder="e.g. left"
              />
            </div>

            <div className="sm:col-span-4">
              <Button
                size="sm"
                variant="outline"
                type="button"
                disabled={
                  updateMutation.isPending ||
                  (!selectedStageId && !newStageName.trim())
                }
                onClick={async () => {
                  try {
                    const base = currentStages.slice();
                    let stageId = selectedStageId;
                    if (!stageId) {
                      const name = newStageName.trim();
                      if (stageNameSetLower.has(name.toLowerCase())) {
                        toast.error("Stage name already exists.");
                        return;
                      }
                      const created =
                        await createStageMutation.mutateAsync(name);
                      stageId = created.id;
                    }
                    base.push({
                      stage_id: stageId,
                      order: addingOrder,
                      label: addingLabel.trim() || undefined,
                    });
                    updateMutation.mutate({ stages: base });
                    setNewStageName("");
                    setSelectedStageId("");
                    setAddingLabel("");
                    setAddingOrder(maxOrder + 1);
                  } catch (e) {
                    toast.error(
                      getSafeErrorMessage(e as Error, "Failed to create stage.")
                    );
                  }
                }}
              >
                Add stage
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
