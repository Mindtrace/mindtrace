"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import {
  listLines,
  createLine,
  updateLine,
  getLineStructure,
  updateLineStructure,
  listPlants,
  listOrganizations,
  listModels,
  listModelDeployments,
  listStageGraphs,
  getSafeErrorMessage,
  isSessionOrAuthError,
} from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { LinesTable } from "@/components/lines/lines-table";
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
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ChevronDown } from "lucide-react";
import type { Line, LineStatus, StageGraph } from "@/lib/api/types";
import { LoadingOverlay } from "@/components/ui/loading-overlay";
import { cn } from "@/lib/utils";
import type { PartGroupItem } from "@/lib/api/line-structure";
import {
  CreateLineForm,
  emptyCreateLineErrors,
  type CreateLineFieldErrors,
  type PartGroupFormItem,
} from "@/components/lines/create-line-form";

const PAGE_SIZE = 10;
const LINE_STATUSES: LineStatus[] = [
  "pending",
  "active",
  "disabled",
  "development",
];

export function LinesPanel() {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [createPlantId, setCreatePlantId] = useState("");
  const [createModelIds, setCreateModelIds] = useState<string[]>([]);
  const [createName, setCreateName] = useState("");
  const [createStatus, setCreateStatus] = useState<LineStatus>("pending");
  const [createPartGroups, setCreatePartGroups] = useState<PartGroupFormItem[]>(
    [{ name: "", parts: [{ part_number: "", stage_graph_id: "" }] }]
  );
  const [createErrors, setCreateErrors] = useState<CreateLineFieldErrors>(() =>
    emptyCreateLineErrors()
  );
  const [editing, setEditing] = useState<Line | null>(null);
  const [editName, setEditName] = useState("");
  const [editStatus, setEditStatus] = useState<LineStatus>("pending");
  const [editPartGroups, setEditPartGroups] = useState<PartGroupItem[]>([]);
  const [isLoadingStructure, setIsLoadingStructure] = useState(false);
  const [editDeploymentIdsToRemove, setEditDeploymentIdsToRemove] = useState<
    string[]
  >([]);
  const [editModelIdsToAdd, setEditModelIdsToAdd] = useState<string[]>([]);
  const [selectedPlantId, setSelectedPlantId] = useState("");
  const [selectedOrgId, setSelectedOrgId] = useState("");
  const [page, setPage] = useState(1);

  const dialogOpen = showCreate || editing !== null;

  function hasNoSpaces(s: string): boolean {
    return !/\s/.test(s);
  }
  function handleNameChange(setter: (v: string) => void, value: string) {
    setter(value.replace(/\s/g, ""));
  }

  function validateCreateLine(): boolean {
    const name = createName.trim();
    const next: CreateLineFieldErrors = emptyCreateLineErrors();

    if (!createPlantId) next.plant = "Select a plant.";
    if (!name) next.name = "Name is required.";
    else if (!hasNoSpaces(name)) next.name = "Name cannot contain spaces.";
    if (createModelIds.length === 0) next.models = "Select at least one model.";

    createPartGroups.forEach((pg, pgIdx) => {
      if (!pg.name.trim()) {
        next.groupName[pgIdx] = "Part group name is required.";
      }
      pg.parts.forEach((p, pIdx) => {
        if (!p.part_number.trim()) {
          next.partNumber[`${pgIdx}-${pIdx}`] = "Part number is required.";
        }
      });
    });

    setCreateErrors(next);
    return (
      !next.plant &&
      !next.models &&
      !next.name &&
      Object.keys(next.groupName).length === 0 &&
      Object.keys(next.partNumber).length === 0
    );
  }

  const { data: orgsData } = useQuery({
    queryKey: ["organizations"],
    queryFn: () => listOrganizations({ limit: 500 }),
  });

  const { data: plantsData } = useQuery({
    queryKey: ["plants", selectedOrgId],
    queryFn: () =>
      listPlants({
        organization_id: selectedOrgId || undefined,
        limit: 500,
      }),
  });

  const { data: modelsData } = useQuery({
    queryKey: ["models"],
    queryFn: () => listModels({ limit: 500 }),
  });

  const { data: deploymentsData } = useQuery({
    queryKey: ["model-deployments", editing?.id],
    queryFn: () => listModelDeployments({ line_id: editing!.id, limit: 500 }),
    enabled: !!editing?.id,
  });

  const { data: stageGraphsData } = useQuery({
    queryKey: ["stage-graphs"],
    queryFn: () => listStageGraphs({ limit: 500 }),
  });
  const stageGraphs = stageGraphsData?.items ?? [];

  const { data, isLoading, error } = useQuery({
    queryKey: ["lines", selectedOrgId, selectedPlantId, page],
    queryFn: () =>
      listLines({
        organization_id: selectedOrgId || undefined,
        plant_id: selectedPlantId || undefined,
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
      }),
  });

  const createMutation = useMutation({
    mutationFn: (payload: {
      plant_id: string;
      model_ids: string[];
      name: string;
      status?: LineStatus;
      part_groups: PartGroupFormItem[];
    }) =>
      createLine({
        ...payload,
        part_groups: payload.part_groups.map((pg) => ({
          name: pg.name || undefined,
          parts: pg.parts.map((p) => ({
            part_number: p.part_number || undefined,
            stage_graph_id: p.stage_graph_id || undefined,
            stage_graph_name: p.stage_graph_name || undefined,
          })),
        })),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["lines"] });
      setCreatePlantId("");
      setCreateModelIds([]);
      setCreateName("");
      setCreateStatus("pending");
      setCreatePartGroups([
        { name: "", parts: [{ part_number: "", stage_graph_id: "" }] },
      ]);
      setCreateErrors(emptyCreateLineErrors());
      toast.success("Line created successfully.");
      setShowCreate(false);
    },
    onError: (err: Error) => {
      if (!isSessionOrAuthError(err))
        toast.error(getSafeErrorMessage(err, "Failed to create line."));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      name,
      status,
      deployment_ids_to_remove,
      model_ids_to_add,
    }: {
      id: string;
      name?: string;
      status?: LineStatus;
      deployment_ids_to_remove?: string[];
      model_ids_to_add?: string[];
    }) =>
      updateLine(id, {
        name,
        status,
        deployment_ids_to_remove,
        model_ids_to_add,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["lines"] });
      queryClient.invalidateQueries({ queryKey: ["model-deployments"] });
      toast.success("Line updated successfully.");
      setEditing(null);
      setEditDeploymentIdsToRemove([]);
      setEditModelIdsToAdd([]);
    },
    onError: (err: Error) => {
      if (!isSessionOrAuthError(err))
        toast.error(getSafeErrorMessage(err, "Failed to update line."));
    },
  });

  const updateStructureMutation = useMutation({
    mutationFn: (payload: { lineId: string; part_groups: PartGroupItem[] }) =>
      updateLineStructure(payload.lineId, { part_groups: payload.part_groups }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["line-structure"] });
      queryClient.invalidateQueries({ queryKey: ["lines"] });
    },
    onError: (err: Error) => {
      if (!isSessionOrAuthError(err))
        toast.error(getSafeErrorMessage(err, "Failed to update structure."));
    },
  });

  function closeDialog() {
    setShowCreate(false);
    setEditing(null);
    setEditDeploymentIdsToRemove([]);
    setEditModelIdsToAdd([]);
    setEditPartGroups([]);
    setCreateErrors(emptyCreateLineErrors());
  }

  function startEdit(line: Line) {
    setEditing(line);
    setEditName(line.name);
    setEditStatus(line.status);
    setEditDeploymentIdsToRemove([]);
    setEditModelIdsToAdd([]);
    setEditPartGroups([]);
    setIsLoadingStructure(true);
    void (async () => {
      try {
        const s = await getLineStructure(line.id);
        setEditPartGroups(s.part_groups);
      } catch (e) {
        if (!isSessionOrAuthError(e))
          toast.error(getSafeErrorMessage(e, "Failed to load part groups."));
      } finally {
        setIsLoadingStructure(false);
      }
    })();
  }

  function statusBadge(status: LineStatus) {
    const variant =
      status === "active"
        ? "default"
        : status === "disabled"
          ? "outline"
          : "secondary";
    return (
      <Badge variant={variant} className="font-normal capitalize">
        {status}
      </Badge>
    );
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

  const lines = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const start = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const end = Math.min(page * PAGE_SIZE, total);
  const orgs = orgsData?.items ?? [];
  const plants = plantsData?.items ?? [];
  const models = modelsData?.items ?? [];
  const isEdit = editing !== null;
  const deployments = deploymentsData?.items ?? [];
  const plantNameById = new Map(plants.map((p) => [p.id, p.name] as const));

  const activeDeployments = deployments.filter(
    (d) => d.deployment_status === "active"
  );
  const visibleDeployments = activeDeployments.filter(
    (d) => !editDeploymentIdsToRemove.includes(d.id)
  );
  const deployedModelIds = new Set(visibleDeployments.map((d) => d.model_id));

  const availableModelsToAdd = models.filter(
    (m) => !deployedModelIds.has(m.id)
  );

  return (
    <div className="space-y-6">
      <Dialog open={dialogOpen} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent className="flex max-h-[90vh] flex-col sm:max-w-md">
          <DialogHeader className="shrink-0">
            <DialogTitle>{isEdit ? "Edit line" : "Create line"}</DialogTitle>
            <DialogDescription>
              {isEdit
                ? "Update the line name, status, and model deployments (take down or add)."
                : "Add a new line. Select a plant and enter a name."}
            </DialogDescription>
          </DialogHeader>

          <div className="min-h-0 flex-1 overflow-y-auto pr-1">
            {isEdit && editing ? (
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  const name = editName.trim() || undefined;
                  if (name !== undefined && !hasNoSpaces(name)) {
                    toast.error("Line name cannot contain spaces.");
                    return;
                  }
                  try {
                    await updateStructureMutation.mutateAsync({
                      lineId: editing.id,
                      part_groups: editPartGroups,
                    });
                    await updateMutation.mutateAsync({
                      id: editing.id,
                      name,
                      status: editStatus,
                      deployment_ids_to_remove: editDeploymentIdsToRemove.length
                        ? editDeploymentIdsToRemove
                        : undefined,
                      model_ids_to_add: editModelIdsToAdd.length
                        ? editModelIdsToAdd
                        : undefined,
                    });
                  } catch {
                    // handled by mutation onError
                  }
                }}
                className="space-y-4"
              >
                <div className="space-y-2">
                  <Label htmlFor="edit-line-name">Name</Label>
                  <Input
                    id="edit-line-name"
                    value={editName}
                    onChange={(e) =>
                      handleNameChange(setEditName, e.target.value)
                    }
                    placeholder="Line name"
                    disabled={updateMutation.isPending}
                  />
                </div>

                <div className="space-y-2">
                  <Label>Status</Label>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="outline"
                        className="w-full justify-between"
                      >
                        <span className="capitalize">{editStatus}</span>
                        <ChevronDown className="h-4 w-4 opacity-50" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent
                      align="start"
                      className="w-[var(--radix-dropdown-menu-trigger-width)]"
                    >
                      {LINE_STATUSES.map((s) => (
                        <DropdownMenuItem
                          key={s}
                          onClick={() => setEditStatus(s)}
                          className="capitalize"
                        >
                          {s}
                        </DropdownMenuItem>
                      ))}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>

                <div className="space-y-2">
                  <Label>Part groups & stage graphs</Label>
                  <div className="space-y-3 rounded-md border p-3">
                    {isLoadingStructure ? (
                      <p className="text-sm text-muted-foreground">
                        Loading part groups…
                      </p>
                    ) : editPartGroups.length === 0 ? (
                      <p className="text-sm text-muted-foreground">
                        No part groups found for this line.
                      </p>
                    ) : (
                      <div className="space-y-3">
                        {editPartGroups.map((pg, pgIdx) => (
                          <div
                            key={pg.id ?? pgIdx}
                            className="rounded-md border p-3"
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex-1 space-y-2">
                                <Label htmlFor={`edit-pg-name-${pgIdx}`}>
                                  Part group name
                                </Label>
                                <Input
                                  id={`edit-pg-name-${pgIdx}`}
                                  value={pg.name}
                                  onChange={(e) => {
                                    const v = e.target.value;
                                    setEditPartGroups((prev) =>
                                      prev.map((x, i) =>
                                        i === pgIdx ? { ...x, name: v } : x
                                      )
                                    );
                                  }}
                                />
                              </div>
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                onClick={() =>
                                  setEditPartGroups((prev) =>
                                    prev.filter((_, i) => i !== pgIdx)
                                  )
                                }
                              >
                                Remove group
                              </Button>
                            </div>

                            <div className="mt-3 space-y-2">
                              <div className="flex items-center justify-between">
                                <Label>Parts</Label>
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="outline"
                                  onClick={() =>
                                    setEditPartGroups((prev) =>
                                      prev.map((x, i) =>
                                        i === pgIdx
                                          ? {
                                              ...x,
                                              parts: [
                                                ...x.parts,
                                                {
                                                  part_number: "",
                                                  stage_graph_id: null,
                                                },
                                              ],
                                            }
                                          : x
                                      )
                                    )
                                  }
                                >
                                  Add part
                                </Button>
                              </div>

                              {pg.parts.map((p, pIdx) => (
                                <div
                                  key={p.id ?? pIdx}
                                  className="rounded-md border p-3"
                                >
                                  <div className="flex items-end justify-between gap-2">
                                    <div className="flex-1 space-y-2">
                                      <Label
                                        htmlFor={`edit-part-number-${pgIdx}-${pIdx}`}
                                      >
                                        Part number
                                      </Label>
                                      <Input
                                        id={`edit-part-number-${pgIdx}-${pIdx}`}
                                        value={p.part_number}
                                        onChange={(e) => {
                                          const v = e.target.value;
                                          setEditPartGroups((prev) =>
                                            prev.map((x, i) =>
                                              i === pgIdx
                                                ? {
                                                    ...x,
                                                    parts: x.parts.map(
                                                      (pp, j) =>
                                                        j === pIdx
                                                          ? {
                                                              ...pp,
                                                              part_number: v,
                                                            }
                                                          : pp
                                                    ),
                                                  }
                                                : x
                                            )
                                          );
                                        }}
                                      />
                                    </div>
                                    <Button
                                      type="button"
                                      size="sm"
                                      variant="outline"
                                      onClick={() =>
                                        setEditPartGroups((prev) =>
                                          prev.map((x, i) =>
                                            i === pgIdx
                                              ? {
                                                  ...x,
                                                  parts: x.parts.filter(
                                                    (_, j) => j !== pIdx
                                                  ),
                                                }
                                              : x
                                          )
                                        )
                                      }
                                    >
                                      Remove part
                                    </Button>
                                  </div>

                                  <div className="mt-3 space-y-2">
                                    <Label
                                      htmlFor={`edit-stage-graph-${pgIdx}-${pIdx}`}
                                    >
                                      Stage graph
                                    </Label>
                                    <select
                                      id={`edit-stage-graph-${pgIdx}-${pIdx}`}
                                      className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
                                      value={p.stage_graph_id ?? ""}
                                      onChange={(e) => {
                                        const v = e.target.value;
                                        setEditPartGroups((prev) =>
                                          prev.map((x, i) =>
                                            i === pgIdx
                                              ? {
                                                  ...x,
                                                  parts: x.parts.map((pp, j) =>
                                                    j === pIdx
                                                      ? {
                                                          ...pp,
                                                          stage_graph_id:
                                                            v || null,
                                                        }
                                                      : pp
                                                  ),
                                                }
                                              : x
                                          )
                                        );
                                      }}
                                    >
                                      <option value="">None</option>
                                      {stageGraphs.map((g: StageGraph) => (
                                        <option key={g.id} value={g.id}>
                                          {g.name}
                                        </option>
                                      ))}
                                    </select>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    <Button
                      type="button"
                      variant="outline"
                      onClick={() =>
                        setEditPartGroups((prev) => [
                          ...prev,
                          { name: "New group", parts: [] },
                        ])
                      }
                    >
                      Add part group
                    </Button>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Model deployments</Label>
                  <div className="space-y-2 rounded-md border p-3">
                    {visibleDeployments.length === 0 ? (
                      <p className="text-sm text-muted-foreground">
                        No active deployments.
                      </p>
                    ) : (
                      <div className="space-y-2">
                        {visibleDeployments.map((d) => (
                          <div
                            key={d.id}
                            className="flex items-center justify-between gap-2"
                          >
                            <div className="min-w-0">
                              <div className="truncate text-sm font-medium">
                                {d.model_name ?? d.model_id}
                              </div>
                              <div className="truncate text-xs text-muted-foreground">
                                {d.model_server_url}
                              </div>
                            </div>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              onClick={() =>
                                setEditDeploymentIdsToRemove((prev) => [
                                  ...prev,
                                  d.id,
                                ])
                              }
                            >
                              Remove
                            </Button>
                          </div>
                        ))}
                      </div>
                    )}

                    <div className="pt-2">
                      <Label className="text-xs text-muted-foreground">
                        Add deployment
                      </Label>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="outline"
                            className="mt-1 w-full justify-between"
                          >
                            {editModelIdsToAdd.length
                              ? `${editModelIdsToAdd.length} selected`
                              : "Select models"}
                            <ChevronDown className="h-4 w-4 opacity-50" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent
                          align="start"
                          className="w-[var(--radix-dropdown-menu-trigger-width)]"
                        >
                          {availableModelsToAdd.length === 0 ? (
                            <DropdownMenuItem disabled>
                              No models available
                            </DropdownMenuItem>
                          ) : (
                            availableModelsToAdd.map((m) => {
                              const checked = editModelIdsToAdd.includes(m.id);
                              return (
                                <DropdownMenuCheckboxItem
                                  key={m.id}
                                  checked={checked}
                                  onSelect={(e) => e.preventDefault()}
                                  onCheckedChange={(next) => {
                                    setEditModelIdsToAdd((prev) =>
                                      next
                                        ? [...prev, m.id]
                                        : prev.filter((id) => id !== m.id)
                                    );
                                  }}
                                >
                                  {m.name}
                                </DropdownMenuCheckboxItem>
                              );
                            })
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </div>
                </div>

                <DialogFooter className="shrink-0">
                  <Button type="button" variant="outline" onClick={closeDialog}>
                    Cancel
                  </Button>
                  <Button type="submit" disabled={updateMutation.isPending}>
                    {updateMutation.isPending ? "Saving…" : "Save"}
                  </Button>
                </DialogFooter>
              </form>
            ) : (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!validateCreateLine()) {
                    toast.error("Please fix the highlighted fields.");
                    return;
                  }
                  const name = createName.trim();
                  createMutation.mutate({
                    plant_id: createPlantId,
                    model_ids: createModelIds,
                    name,
                    status: createStatus,
                    part_groups: createPartGroups,
                  });
                }}
                className="space-y-4"
                noValidate
              >
                <div className="space-y-2">
                  <Label htmlFor="create-line-plant">
                    Plant{" "}
                    <span className="text-destructive" aria-hidden>
                      *
                    </span>
                  </Label>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        id="create-line-plant"
                        type="button"
                        variant="outline"
                        aria-required
                        aria-invalid={!!createErrors.plant}
                        aria-describedby={
                          createErrors.plant
                            ? "create-line-plant-error"
                            : undefined
                        }
                        className={cn(
                          "w-full justify-between",
                          createErrors.plant &&
                            "border-destructive ring-1 ring-destructive"
                        )}
                      >
                        {plants.find((p) => p.id === createPlantId)?.name ??
                          "Select plant"}
                        <ChevronDown className="h-4 w-4 opacity-50" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent
                      align="start"
                      className="w-[var(--radix-dropdown-menu-trigger-width)]"
                    >
                      {plants.map((p) => (
                        <DropdownMenuItem
                          key={p.id}
                          onClick={() => {
                            setCreatePlantId(p.id);
                            setCreateErrors((prev) => ({
                              ...prev,
                              plant: undefined,
                            }));
                          }}
                        >
                          {p.name}
                        </DropdownMenuItem>
                      ))}
                    </DropdownMenuContent>
                  </DropdownMenu>
                  {createErrors.plant ? (
                    <p
                      id="create-line-plant-error"
                      className="text-sm text-destructive"
                      role="alert"
                    >
                      {createErrors.plant}
                    </p>
                  ) : null}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="create-line-models">
                    Models{" "}
                    <span className="text-destructive" aria-hidden>
                      *
                    </span>
                  </Label>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        id="create-line-models"
                        type="button"
                        variant="outline"
                        aria-required
                        aria-invalid={!!createErrors.models}
                        aria-describedby={
                          createErrors.models
                            ? "create-line-models-error"
                            : undefined
                        }
                        className={cn(
                          "w-full justify-between",
                          createErrors.models &&
                            "border-destructive ring-1 ring-destructive"
                        )}
                      >
                        {createModelIds.length
                          ? `${createModelIds.length} selected`
                          : "Select models"}
                        <ChevronDown className="h-4 w-4 opacity-50" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent
                      align="start"
                      className="w-[var(--radix-dropdown-menu-trigger-width)]"
                    >
                      {models.map((m) => {
                        const checked = createModelIds.includes(m.id);
                        return (
                          <DropdownMenuCheckboxItem
                            key={m.id}
                            checked={checked}
                            onSelect={(e) => e.preventDefault()}
                            onCheckedChange={(next) => {
                              setCreateModelIds((prev) =>
                                next
                                  ? [...prev, m.id]
                                  : prev.filter((id) => id !== m.id)
                              );
                              setCreateErrors((prev) => ({
                                ...prev,
                                models: undefined,
                              }));
                            }}
                          >
                            {m.name}
                          </DropdownMenuCheckboxItem>
                        );
                      })}
                    </DropdownMenuContent>
                  </DropdownMenu>
                  {createErrors.models ? (
                    <p
                      id="create-line-models-error"
                      className="text-sm text-destructive"
                      role="alert"
                    >
                      {createErrors.models}
                    </p>
                  ) : null}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="create-line-name">
                    Name{" "}
                    <span className="text-destructive" aria-hidden>
                      *
                    </span>
                  </Label>
                  <Input
                    id="create-line-name"
                    name="lineName"
                    value={createName}
                    onChange={(e) => {
                      handleNameChange(setCreateName, e.target.value);
                      setCreateErrors((prev) => ({
                        ...prev,
                        name: undefined,
                      }));
                    }}
                    placeholder="Line name"
                    required
                    aria-required
                    aria-invalid={!!createErrors.name}
                    aria-describedby={
                      createErrors.name ? "create-line-name-error" : undefined
                    }
                    className={cn(createErrors.name && "border-destructive")}
                    disabled={createMutation.isPending}
                  />
                  {createErrors.name ? (
                    <p
                      id="create-line-name-error"
                      className="text-sm text-destructive"
                      role="alert"
                    >
                      {createErrors.name}
                    </p>
                  ) : null}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="create-line-status">Status</Label>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        id="create-line-status"
                        type="button"
                        variant="outline"
                        className="w-full justify-between"
                      >
                        <span className="capitalize">{createStatus}</span>
                        <ChevronDown className="h-4 w-4 opacity-50" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent
                      align="start"
                      className="w-[var(--radix-dropdown-menu-trigger-width)]"
                    >
                      {LINE_STATUSES.map((s) => (
                        <DropdownMenuItem
                          key={s}
                          onClick={() => setCreateStatus(s)}
                          className="capitalize"
                        >
                          {s}
                        </DropdownMenuItem>
                      ))}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label>
                      Part groups{" "}
                      <span className="text-destructive" aria-hidden>
                        *
                      </span>
                    </Label>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        setCreatePartGroups((prev) => [
                          ...prev,
                          {
                            name: "",
                            parts: [{ part_number: "", stage_graph_id: "" }],
                          },
                        ])
                      }
                    >
                      <Plus className="mr-1 h-4 w-4" />
                      Add part group
                    </Button>
                  </div>

                  <div className="space-y-3">
                    {createPartGroups.map((pg, pgIdx) => (
                      <div
                        key={pgIdx}
                        className={cn(
                          "rounded-md border p-3",
                          (createErrors.groupName[pgIdx] ||
                            Object.keys(createErrors.partNumber).some((k) =>
                              k.startsWith(`${pgIdx}-`)
                            )) &&
                            "border-destructive ring-1 ring-destructive/40"
                        )}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 space-y-2">
                            <Label htmlFor={`create-pg-name-${pgIdx}`}>
                              Part group name{" "}
                              <span className="text-destructive" aria-hidden>
                                *
                              </span>
                            </Label>
                            <Input
                              id={`create-pg-name-${pgIdx}`}
                              value={pg.name}
                              required
                              aria-required
                              aria-invalid={!!createErrors.groupName[pgIdx]}
                              aria-describedby={
                                createErrors.groupName[pgIdx]
                                  ? `create-pg-name-${pgIdx}-error`
                                  : undefined
                              }
                              className={cn(
                                createErrors.groupName[pgIdx] &&
                                  "border-destructive"
                              )}
                              onChange={(e) => {
                                const v = e.target.value;
                                setCreatePartGroups((prev) =>
                                  prev.map((x, i) =>
                                    i === pgIdx ? { ...x, name: v } : x
                                  )
                                );
                                setCreateErrors((prev) => {
                                  const gn = { ...prev.groupName };
                                  delete gn[pgIdx];
                                  return { ...prev, groupName: gn };
                                });
                              }}
                              placeholder="e.g. Group A"
                            />
                            {createErrors.groupName[pgIdx] ? (
                              <p
                                id={`create-pg-name-${pgIdx}-error`}
                                className="text-sm text-destructive"
                                role="alert"
                              >
                                {createErrors.groupName[pgIdx]}
                              </p>
                            ) : null}
                          </div>
                          <Button
                            type="button"
                            size="icon"
                            variant="outline"
                            className="mt-7"
                            onClick={() =>
                              setCreatePartGroups((prev) =>
                                prev.filter((_, i) => i !== pgIdx)
                              )
                            }
                            disabled={createPartGroups.length <= 1}
                            aria-label="Remove part group"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>

                        <div className="mt-3 space-y-2">
                          <div className="flex items-center justify-between">
                            <Label>Parts</Label>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              onClick={() => {
                                setCreatePartGroups((prev) =>
                                  prev.map((x, i) =>
                                    i === pgIdx
                                      ? {
                                          ...x,
                                          parts: [
                                            ...x.parts,
                                            {
                                              part_number: "",
                                              stage_graph_id: "",
                                            },
                                          ],
                                        }
                                      : x
                                  )
                                );
                              }}
                            >
                              <Plus className="mr-1 h-4 w-4" />
                              Add part
                            </Button>
                          </div>

                          {pg.parts.map((p, pIdx) => (
                            <div key={pIdx} className="flex items-end gap-2">
                              <div className="flex-1 space-y-2">
                                <Label htmlFor={`create-part-${pgIdx}-${pIdx}`}>
                                  Part number{" "}
                                  <span
                                    className="text-destructive"
                                    aria-hidden
                                  >
                                    *
                                  </span>
                                </Label>
                                <Input
                                  id={`create-part-${pgIdx}-${pIdx}`}
                                  value={p.part_number}
                                  required
                                  aria-required
                                  aria-invalid={
                                    !!createErrors.partNumber[
                                      `${pgIdx}-${pIdx}`
                                    ]
                                  }
                                  aria-describedby={
                                    createErrors.partNumber[`${pgIdx}-${pIdx}`]
                                      ? `create-part-${pgIdx}-${pIdx}-error`
                                      : undefined
                                  }
                                  className={cn(
                                    createErrors.partNumber[
                                      `${pgIdx}-${pIdx}`
                                    ] && "border-destructive"
                                  )}
                                  onChange={(e) => {
                                    const v = e.target.value;
                                    setCreatePartGroups((prev) =>
                                      prev.map((x, i) =>
                                        i === pgIdx
                                          ? {
                                              ...x,
                                              parts: x.parts.map((pp, j) =>
                                                j === pIdx
                                                  ? { ...pp, part_number: v }
                                                  : pp
                                              ),
                                            }
                                          : x
                                      )
                                    );
                                    const key = `${pgIdx}-${pIdx}`;
                                    setCreateErrors((prev) => {
                                      const pn = { ...prev.partNumber };
                                      delete pn[key];
                                      return { ...prev, partNumber: pn };
                                    });
                                  }}
                                  placeholder="e.g. 123-ABC"
                                />
                                {createErrors.partNumber[`${pgIdx}-${pIdx}`] ? (
                                  <p
                                    id={`create-part-${pgIdx}-${pIdx}-error`}
                                    className="text-sm text-destructive"
                                    role="alert"
                                  >
                                    {
                                      createErrors.partNumber[
                                        `${pgIdx}-${pIdx}`
                                      ]
                                    }
                                  </p>
                                ) : null}
                              </div>
                              <div className="w-[220px] space-y-2">
                                <Label
                                  htmlFor={`create-stage-graph-${pgIdx}-${pIdx}`}
                                >
                                  Stage graph
                                </Label>
                                <select
                                  id={`create-stage-graph-${pgIdx}-${pIdx}`}
                                  className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
                                  value={p.stage_graph_id ?? ""}
                                  onChange={(e) => {
                                    const v = e.target.value;
                                    setCreatePartGroups((prev) =>
                                      prev.map((x, i) =>
                                        i === pgIdx
                                          ? {
                                              ...x,
                                              parts: x.parts.map((pp, j) =>
                                                j === pIdx
                                                  ? {
                                                      ...pp,
                                                      stage_graph_id: v,
                                                      stage_graph_name: "",
                                                    }
                                                  : pp
                                              ),
                                            }
                                          : x
                                      )
                                    );
                                  }}
                                >
                                  <option value="">None</option>
                                  {stageGraphs.map((g: StageGraph) => (
                                    <option key={g.id} value={g.id}>
                                      {g.name}
                                    </option>
                                  ))}
                                </select>
                                <Input
                                  id={`create-stage-graph-name-${pgIdx}-${pIdx}`}
                                  value={p.stage_graph_name ?? ""}
                                  onChange={(e) => {
                                    const v = e.target.value;
                                    setCreatePartGroups((prev) =>
                                      prev.map((x, i) =>
                                        i === pgIdx
                                          ? {
                                              ...x,
                                              parts: x.parts.map((pp, j) =>
                                                j === pIdx
                                                  ? {
                                                      ...pp,
                                                      stage_graph_name: v,
                                                      stage_graph_id: "",
                                                    }
                                                  : pp
                                              ),
                                            }
                                          : x
                                      )
                                    );
                                  }}
                                  placeholder="Or create new by name…"
                                />
                              </div>
                              <Button
                                type="button"
                                size="icon"
                                variant="outline"
                                onClick={() => {
                                  setCreatePartGroups((prev) =>
                                    prev.map((x, i) =>
                                      i === pgIdx
                                        ? {
                                            ...x,
                                            parts: x.parts.filter(
                                              (_, j) => j !== pIdx
                                            ),
                                          }
                                        : x
                                    )
                                  );
                                }}
                                disabled={pg.parts.length <= 1}
                                aria-label="Remove part"
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <DialogFooter className="shrink-0">
                  <Button type="button" variant="outline" onClick={closeDialog}>
                    Cancel
                  </Button>
                  <Button type="submit" disabled={createMutation.isPending}>
                    {createMutation.isPending ? "Creating…" : "Create"}
                  </Button>
                </DialogFooter>
              </form>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4 py-4">
          <div className="flex items-center gap-2">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" className="justify-between">
                  {orgs.find((o) => o.id === selectedOrgId)?.name ?? "All orgs"}
                  <ChevronDown className="ml-2 h-4 w-4 opacity-50" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                <DropdownMenuItem onClick={() => setSelectedOrgId("")}>
                  All orgs
                </DropdownMenuItem>
                {orgs.map((o) => (
                  <DropdownMenuItem
                    key={o.id}
                    onClick={() => setSelectedOrgId(o.id)}
                  >
                    {o.name}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" className="justify-between">
                  {plants.find((p) => p.id === selectedPlantId)?.name ??
                    "All plants"}
                  <ChevronDown className="ml-2 h-4 w-4 opacity-50" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                <DropdownMenuItem onClick={() => setSelectedPlantId("")}>
                  All plants
                </DropdownMenuItem>
                {plants.map((p) => (
                  <DropdownMenuItem
                    key={p.id}
                    onClick={() => setSelectedPlantId(p.id)}
                  >
                    {p.name}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          <Button
            onClick={() => {
              setCreateErrors(emptyCreateLineErrors());
              setShowCreate(true);
            }}
          >
            Create line
          </Button>
        </CardHeader>
        <CardContent>
          {lines.length === 0 ? (
            <p className="py-8 text-center text-muted-foreground">
              No lines yet.
            </p>
          ) : (
            <LinesTable
              lines={lines}
              plantNameById={plantNameById}
              statusBadge={statusBadge}
              onEdit={startEdit}
            />
          )}

          {total > 0 ? (
            <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t pt-4">
              <p className="text-sm text-muted-foreground">
                Showing {start}–{end} of {total}
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage(Math.max(1, page - 1))}
                  disabled={page <= 1}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage(Math.min(totalPages, page + 1))}
                  disabled={page >= totalPages}
                >
                  Next
                </Button>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
