"use client";

import { ChevronDown } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { LineStatus, Model, ModelDeployment, StageGraph } from "@/lib/api/types";
import type { PartGroupItem } from "@/lib/api/line-structure";

export function EditLineForm(props: {
  LINE_STATUSES: LineStatus[];
  editName: string;
  setEditName: (v: string) => void;
  editStatus: LineStatus;
  setEditStatus: (v: LineStatus) => void;
  editPartGroups: PartGroupItem[];
  setEditPartGroups: (v: PartGroupItem[] | ((prev: PartGroupItem[]) => PartGroupItem[])) => void;
  isLoadingStructure: boolean;
  stageGraphs: StageGraph[];
  visibleDeployments: ModelDeployment[];
  setEditDeploymentIdsToRemove: (v: string[] | ((prev: string[]) => string[])) => void;
  availableModelsToAdd: Model[];
  editModelIdsToAdd: string[];
  setEditModelIdsToAdd: (v: string[] | ((prev: string[]) => string[])) => void;
  updatePending: boolean;
  onCancel: () => void;
  onSubmit: () => Promise<void>;
  hasNoSpaces: (s: string) => boolean;
  handleNameChange: (setter: (v: string) => void, value: string) => void;
}) {
  const {
    LINE_STATUSES,
    editName,
    setEditName,
    editStatus,
    setEditStatus,
    editPartGroups,
    setEditPartGroups,
    isLoadingStructure,
    stageGraphs,
    visibleDeployments,
    setEditDeploymentIdsToRemove,
    availableModelsToAdd,
    editModelIdsToAdd,
    setEditModelIdsToAdd,
    updatePending,
    onCancel,
    onSubmit,
    hasNoSpaces,
    handleNameChange,
  } = props;

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        const name = editName.trim() || undefined;
        if (name !== undefined && !hasNoSpaces(name)) return;
        await onSubmit();
      }}
      className="space-y-4"
    >
      <div className="space-y-2">
        <Label htmlFor="edit-line-name">Name</Label>
        <Input
          id="edit-line-name"
          value={editName}
          onChange={(e) => handleNameChange(setEditName, e.target.value)}
          placeholder="Line name"
          disabled={updatePending}
        />
      </div>

      <div className="space-y-2">
        <Label>Status</Label>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" className="w-full justify-between">
              <span className="capitalize">{editStatus}</span>
              <ChevronDown className="h-4 w-4 opacity-50" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="start"
            className="w-[var(--radix-dropdown-menu-trigger-width)]"
          >
            {LINE_STATUSES.map((s) => (
              <DropdownMenuItem key={s} onClick={() => setEditStatus(s)} className="capitalize">
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
            <p className="text-sm text-muted-foreground">Loading part groups…</p>
          ) : editPartGroups.length === 0 ? (
            <p className="text-sm text-muted-foreground">No part groups found for this line.</p>
          ) : (
            <div className="space-y-3">
              {editPartGroups.map((pg, pgIdx) => (
                <div key={pg.id ?? pgIdx} className="rounded-md border p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 space-y-2">
                      <Label htmlFor={`edit-pg-name-${pgIdx}`}>Part group name</Label>
                      <Input
                        id={`edit-pg-name-${pgIdx}`}
                        value={pg.name}
                        onChange={(e) => {
                          const v = e.target.value;
                          setEditPartGroups((prev) =>
                            prev.map((x, i) => (i === pgIdx ? { ...x, name: v } : x))
                          );
                        }}
                      />
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => setEditPartGroups((prev) => prev.filter((_, i) => i !== pgIdx))}
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
                                      { part_number: "", stage_graph_id: "", stage_graph_name: "" },
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
                      <div key={pIdx} className="flex items-end gap-2">
                        <div className="flex-1 space-y-2">
                          <Label htmlFor={`edit-part-${pgIdx}-${pIdx}`}>Part number</Label>
                          <Input
                            id={`edit-part-${pgIdx}-${pIdx}`}
                            value={p.part_number}
                            onChange={(e) => {
                              const v = e.target.value;
                              setEditPartGroups((prev) =>
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
                            }}
                          />
                        </div>
                        <div className="w-[220px] space-y-2">
                          <Label htmlFor={`edit-stage-graph-${pgIdx}-${pIdx}`}>Stage graph</Label>
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
                        </div>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            setEditPartGroups((prev) =>
                              prev.map((x, i) =>
                                i === pgIdx
                                  ? { ...x, parts: x.parts.filter((_, j) => j !== pIdx) }
                                  : x
                              )
                            )
                          }
                        >
                          Remove
                        </Button>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="space-y-2">
        <Label>Active deployments</Label>
        <div className="flex flex-wrap gap-2">
          {visibleDeployments.length === 0 ? (
            <p className="text-sm text-muted-foreground">No active deployments.</p>
          ) : (
            visibleDeployments.map((d) => (
              <Badge
                key={d.id}
                variant="secondary"
                className="cursor-pointer select-none"
                onClick={() => setEditDeploymentIdsToRemove((prev) => [...prev, d.id])}
                title="Click to mark for removal"
              >
                {d.model_name ?? d.model_id}
              </Badge>
            ))
          )}
        </div>
      </div>

      <div className="space-y-2">
        <Label>Add models</Label>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" className="w-full justify-between">
              {editModelIdsToAdd.length ? `${editModelIdsToAdd.length} selected` : "Select models"}
              <ChevronDown className="h-4 w-4 opacity-50" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="start"
            className="w-[var(--radix-dropdown-menu-trigger-width)]"
          >
            {availableModelsToAdd.length === 0 ? (
              <DropdownMenuItem disabled>No models available</DropdownMenuItem>
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
                        next ? [...prev, m.id] : prev.filter((id) => id !== m.id)
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

      <DialogFooter className="shrink-0">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={updatePending}>
          {updatePending ? "Saving…" : "Save"}
        </Button>
      </DialogFooter>
    </form>
  );
}

