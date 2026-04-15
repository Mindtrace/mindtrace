"use client";

import { ChevronDown, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DialogFooter,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import type { LineStatus, Plant, Model, StageGraph } from "@/lib/api/types";

export interface PartGroupFormItem {
  name: string;
  parts: {
    part_number: string;
    stage_graph_id?: string;
    stage_graph_name?: string;
  }[];
}

export type CreateLineFieldErrors = {
  plant?: string;
  models?: string;
  name?: string;
  groupName: Record<number, string>;
  partNumber: Record<string, string>;
};

export function emptyCreateLineErrors(): CreateLineFieldErrors {
  return { groupName: {}, partNumber: {} };
}

export function CreateLineForm(props: {
  LINE_STATUSES: LineStatus[];
  plants: Plant[];
  models: Model[];
  stageGraphs: StageGraph[];

  createPlantId: string;
  setCreatePlantId: (v: string) => void;
  createModelIds: string[];
  setCreateModelIds: (v: string[] | ((prev: string[]) => string[])) => void;
  createName: string;
  setCreateName: (v: string) => void;
  createStatus: LineStatus;
  setCreateStatus: (v: LineStatus) => void;
  createPartGroups: PartGroupFormItem[];
  setCreatePartGroups: (
    v: PartGroupFormItem[] | ((prev: PartGroupFormItem[]) => PartGroupFormItem[])
  ) => void;
  createErrors: CreateLineFieldErrors;
  setCreateErrors: (
    v:
      | CreateLineFieldErrors
      | ((prev: CreateLineFieldErrors) => CreateLineFieldErrors)
  ) => void;

  createPending: boolean;
  validateCreateLine: () => boolean;
  handleNameChange: (setter: (v: string) => void, value: string) => void;
  onCancel: () => void;
  onCreate: (payload: {
    plant_id: string;
    model_ids: string[];
    name: string;
    status?: LineStatus;
    part_groups: PartGroupFormItem[];
  }) => void;
}) {
  const {
    LINE_STATUSES,
    plants,
    models,
    stageGraphs,
    createPlantId,
    setCreatePlantId,
    createModelIds,
    setCreateModelIds,
    createName,
    setCreateName,
    createStatus,
    setCreateStatus,
    createPartGroups,
    setCreatePartGroups,
    createErrors,
    setCreateErrors,
    createPending,
    validateCreateLine,
    handleNameChange,
    onCancel,
    onCreate,
  } = props;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!validateCreateLine()) return;
        const name = createName.trim();
        onCreate({
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
          Plant <span className="text-destructive" aria-hidden>*</span>
        </Label>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              id="create-line-plant"
              type="button"
              variant="outline"
              aria-required
              aria-invalid={!!createErrors.plant}
              aria-describedby={createErrors.plant ? "create-line-plant-error" : undefined}
              className={cn(
                "w-full justify-between",
                createErrors.plant && "border-destructive ring-1 ring-destructive"
              )}
            >
              {plants.find((p) => p.id === createPlantId)?.name ?? "Select plant"}
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
                  setCreateErrors((prev) => ({ ...prev, plant: undefined }));
                }}
              >
                {p.name}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        {createErrors.plant ? (
          <p id="create-line-plant-error" className="text-sm text-destructive" role="alert">
            {createErrors.plant}
          </p>
        ) : null}
      </div>

      <div className="space-y-2">
        <Label htmlFor="create-line-models">
          Models <span className="text-destructive" aria-hidden>*</span>
        </Label>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              id="create-line-models"
              type="button"
              variant="outline"
              aria-required
              aria-invalid={!!createErrors.models}
              aria-describedby={createErrors.models ? "create-line-models-error" : undefined}
              className={cn(
                "w-full justify-between",
                createErrors.models && "border-destructive ring-1 ring-destructive"
              )}
            >
              {createModelIds.length ? `${createModelIds.length} selected` : "Select models"}
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
                      next ? [...prev, m.id] : prev.filter((id) => id !== m.id)
                    );
                    setCreateErrors((prev) => ({ ...prev, models: undefined }));
                  }}
                >
                  {m.name}
                </DropdownMenuCheckboxItem>
              );
            })}
          </DropdownMenuContent>
        </DropdownMenu>
        {createErrors.models ? (
          <p id="create-line-models-error" className="text-sm text-destructive" role="alert">
            {createErrors.models}
          </p>
        ) : null}
      </div>

      <div className="space-y-2">
        <Label htmlFor="create-line-name">
          Name <span className="text-destructive" aria-hidden>*</span>
        </Label>
        <Input
          id="create-line-name"
          name="lineName"
          value={createName}
          onChange={(e) => {
            handleNameChange(setCreateName, e.target.value);
            setCreateErrors((prev) => ({ ...prev, name: undefined }));
          }}
          placeholder="Line name"
          required
          aria-required
          aria-invalid={!!createErrors.name}
          aria-describedby={createErrors.name ? "create-line-name-error" : undefined}
          className={cn(createErrors.name && "border-destructive")}
          disabled={createPending}
        />
        {createErrors.name ? (
          <p id="create-line-name-error" className="text-sm text-destructive" role="alert">
            {createErrors.name}
          </p>
        ) : null}
      </div>

      <div className="space-y-2">
        <Label htmlFor="create-line-status">Status</Label>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button id="create-line-status" type="button" variant="outline" className="w-full justify-between">
              <span className="capitalize">{createStatus}</span>
              <ChevronDown className="h-4 w-4 opacity-50" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="start"
            className="w-[var(--radix-dropdown-menu-trigger-width)]"
          >
            {LINE_STATUSES.map((s) => (
              <DropdownMenuItem key={s} onClick={() => setCreateStatus(s)} className="capitalize">
                {s}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label>
            Part groups <span className="text-destructive" aria-hidden>*</span>
          </Label>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() =>
              setCreatePartGroups((prev) => [
                ...prev,
                { name: "", parts: [{ part_number: "", stage_graph_id: "" }] },
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
                  Object.keys(createErrors.partNumber).some((k) => k.startsWith(`${pgIdx}-`))) &&
                  "border-destructive ring-1 ring-destructive/40"
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 space-y-2">
                  <Label htmlFor={`create-pg-name-${pgIdx}`}>
                    Part group name <span className="text-destructive" aria-hidden>*</span>
                  </Label>
                  <Input
                    id={`create-pg-name-${pgIdx}`}
                    value={pg.name}
                    required
                    aria-required
                    aria-invalid={!!createErrors.groupName[pgIdx]}
                    aria-describedby={
                      createErrors.groupName[pgIdx] ? `create-pg-name-${pgIdx}-error` : undefined
                    }
                    className={cn(createErrors.groupName[pgIdx] && "border-destructive")}
                    onChange={(e) => {
                      const v = e.target.value;
                      setCreatePartGroups((prev) =>
                        prev.map((x, i) => (i === pgIdx ? { ...x, name: v } : x))
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
                  onClick={() => setCreatePartGroups((prev) => prev.filter((_, i) => i !== pgIdx))}
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
                                parts: [...x.parts, { part_number: "", stage_graph_id: "" }],
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
                        Part number <span className="text-destructive" aria-hidden>*</span>
                      </Label>
                      <Input
                        id={`create-part-${pgIdx}-${pIdx}`}
                        value={p.part_number}
                        required
                        aria-required
                        aria-invalid={!!createErrors.partNumber[`${pgIdx}-${pIdx}`]}
                        aria-describedby={
                          createErrors.partNumber[`${pgIdx}-${pIdx}`]
                            ? `create-part-${pgIdx}-${pIdx}-error`
                            : undefined
                        }
                        className={cn(
                          createErrors.partNumber[`${pgIdx}-${pIdx}`] && "border-destructive"
                        )}
                        onChange={(e) => {
                          const v = e.target.value;
                          setCreatePartGroups((prev) =>
                            prev.map((x, i) =>
                              i === pgIdx
                                ? {
                                    ...x,
                                    parts: x.parts.map((pp, j) =>
                                      j === pIdx ? { ...pp, part_number: v } : pp
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
                          {createErrors.partNumber[`${pgIdx}-${pIdx}`]}
                        </p>
                      ) : null}
                    </div>
                    <div className="w-[220px] space-y-2">
                      <Label htmlFor={`create-stage-graph-${pgIdx}-${pIdx}`}>Stage graph</Label>
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
                                        ? { ...pp, stage_graph_id: v, stage_graph_name: "" }
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
                                        ? { ...pp, stage_graph_name: v, stage_graph_id: "" }
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
                              ? { ...x, parts: x.parts.filter((_, j) => j !== pIdx) }
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
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={createPending}>
          {createPending ? "Creating…" : "Create"}
        </Button>
      </DialogFooter>
    </form>
  );
}

