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
import { EditLineForm } from "@/components/lines/edit-line-form";

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
              <EditLineForm
                LINE_STATUSES={LINE_STATUSES}
                editName={editName}
                setEditName={setEditName}
                editStatus={editStatus}
                setEditStatus={setEditStatus}
                editPartGroups={editPartGroups}
                setEditPartGroups={setEditPartGroups}
                isLoadingStructure={isLoadingStructure}
                stageGraphs={stageGraphs}
                visibleDeployments={visibleDeployments}
                setEditDeploymentIdsToRemove={setEditDeploymentIdsToRemove}
                availableModelsToAdd={availableModelsToAdd}
                editModelIdsToAdd={editModelIdsToAdd}
                setEditModelIdsToAdd={setEditModelIdsToAdd}
                updatePending={updateMutation.isPending}
                onCancel={closeDialog}
                onSubmit={async () => {
                  try {
                    await updateStructureMutation.mutateAsync({
                      lineId: editing.id,
                      part_groups: editPartGroups,
                    });
                    await updateMutation.mutateAsync({
                      id: editing.id,
                      name: editName.trim() || undefined,
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
                hasNoSpaces={hasNoSpaces}
                handleNameChange={handleNameChange}
              />
            ) : (
              <CreateLineForm
                LINE_STATUSES={LINE_STATUSES}
                plants={plants}
                models={models}
                stageGraphs={stageGraphs}
                createPlantId={createPlantId}
                setCreatePlantId={(v) => {
                  setCreatePlantId(v);
                  setCreateErrors((prev) => ({ ...prev, plant: undefined }));
                }}
                createModelIds={createModelIds}
                setCreateModelIds={setCreateModelIds}
                createName={createName}
                setCreateName={setCreateName}
                createStatus={createStatus}
                setCreateStatus={setCreateStatus}
                createPartGroups={createPartGroups}
                setCreatePartGroups={setCreatePartGroups}
                createErrors={createErrors}
                setCreateErrors={setCreateErrors}
                createPending={createMutation.isPending}
                validateCreateLine={() => {
                  const ok = validateCreateLine();
                  if (!ok) toast.error("Please fix the highlighted fields.");
                  return ok;
                }}
                handleNameChange={handleNameChange}
                onCancel={closeDialog}
                onCreate={(payload) => createMutation.mutate(payload)}
              />
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
