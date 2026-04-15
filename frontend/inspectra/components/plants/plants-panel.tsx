"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import {
  listPlants,
  createPlant,
  updatePlant,
  listOrganizations,
  getSafeErrorMessage,
  isSessionOrAuthError,
} from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
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
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ChevronDown } from "lucide-react";
import type { Plant } from "@/lib/api/types";
import { LoadingOverlay } from "@/components/ui/loading-overlay";

const PAGE_SIZE = 10;

export function PlantsPanel() {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [createOrgId, setCreateOrgId] = useState("");
  const [createName, setCreateName] = useState("");
  const [createLocation, setCreateLocation] = useState("");
  const [editing, setEditing] = useState<Plant | null>(null);
  const [editName, setEditName] = useState("");
  const [editLocation, setEditLocation] = useState("");
  const [selectedOrgId, setSelectedOrgId] = useState("");
  const [page, setPage] = useState(1);

  const dialogOpen = showCreate || editing !== null;

  function hasNoSpaces(s: string): boolean {
    return !/\s/.test(s);
  }
  function handleNameChange(setter: (v: string) => void, value: string) {
    setter(value.replace(/\s/g, ""));
  }

  const { data: orgsData } = useQuery({
    queryKey: ["organizations"],
    queryFn: () => listOrganizations({ limit: 500 }),
  });

  const { data, isLoading, error } = useQuery({
    queryKey: ["plants", selectedOrgId, page],
    queryFn: () =>
      listPlants({
        organization_id: selectedOrgId || undefined,
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
      }),
  });

  const createMutation = useMutation({
    mutationFn: (payload: {
      organization_id: string;
      name: string;
      location?: string;
    }) => createPlant(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["plants"] });
      setCreateOrgId("");
      setCreateName("");
      setCreateLocation("");
      toast.success("Plant created successfully.");
      setShowCreate(false);
    },
    onError: (err: Error) => {
      if (!isSessionOrAuthError(err))
        toast.error(getSafeErrorMessage(err, "Failed to create plant."));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      name,
      location,
    }: {
      id: string;
      name?: string;
      location?: string;
    }) => updatePlant(id, { name, location }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["plants"] });
      toast.success("Plant updated successfully.");
      setEditing(null);
    },
    onError: (err: Error) => {
      if (!isSessionOrAuthError(err))
        toast.error(getSafeErrorMessage(err, "Failed to update plant."));
    },
  });

  function closeDialog() {
    setShowCreate(false);
    setEditing(null);
  }

  function startEdit(plant: Plant) {
    setEditing(plant);
    setEditName(plant.name);
    setEditLocation(plant.location ?? "");
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

  const plants = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const start = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const end = Math.min(page * PAGE_SIZE, total);
  const orgs = orgsData?.items ?? [];
  const isEdit = editing !== null;

  return (
    <div className="space-y-6">
      <Dialog open={dialogOpen} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{isEdit ? "Edit plant" : "Create plant"}</DialogTitle>
            <DialogDescription>
              {isEdit
                ? "Update the plant name or location."
                : "Add a new plant. Select an organization and enter a name."}
            </DialogDescription>
          </DialogHeader>

          {isEdit && editing ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const name = editName.trim() || undefined;
                if (name !== undefined && !hasNoSpaces(name)) {
                  toast.error("Plant name cannot contain spaces.");
                  return;
                }
                updateMutation.mutate({
                  id: editing.id,
                  name,
                  location: editLocation.trim() || undefined,
                });
              }}
              className="space-y-4"
            >
              <div className="space-y-2">
                <Label htmlFor="edit-plant-name">Name</Label>
                <Input
                  id="edit-plant-name"
                  value={editName}
                  onChange={(e) =>
                    handleNameChange(setEditName, e.target.value)
                  }
                  placeholder="Plant name (no spaces)"
                  disabled={updateMutation.isPending}
                />
                <p className="text-xs text-muted-foreground">
                  No spaces allowed.
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-plant-location">Location (optional)</Label>
                <Input
                  id="edit-plant-location"
                  value={editLocation}
                  onChange={(e) => setEditLocation(e.target.value)}
                  placeholder="Location"
                  disabled={updateMutation.isPending}
                />
              </div>
              <DialogFooter>
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
                const name = createName.trim();
                if (!createOrgId.trim() || !name) return;
                if (!hasNoSpaces(name)) {
                  toast.error("Plant name cannot contain spaces.");
                  return;
                }
                createMutation.mutate({
                  organization_id: createOrgId,
                  name,
                  location: createLocation.trim() || undefined,
                });
              }}
              className="space-y-4"
            >
              <div className="space-y-2">
                <Label htmlFor="create-plant-org">Organization</Label>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      id="create-plant-org"
                      type="button"
                      variant="outline"
                      className="w-full justify-between font-normal"
                      disabled={createMutation.isPending}
                      aria-label="Select organization"
                    >
                      {orgs.find((o) => o.id === createOrgId)?.name ??
                        "Select organization"}
                      <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start">
                    {orgs.length === 0 ? (
                      <DropdownMenuItem disabled>
                        No organizations available
                      </DropdownMenuItem>
                    ) : (
                      orgs.map((org) => (
                        <DropdownMenuItem
                          key={org.id}
                          onClick={() => setCreateOrgId(org.id)}
                        >
                          {org.name}
                        </DropdownMenuItem>
                      ))
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
              <div className="space-y-2">
                <Label htmlFor="create-plant-name">Name</Label>
                <Input
                  id="create-plant-name"
                  value={createName}
                  onChange={(e) =>
                    handleNameChange(setCreateName, e.target.value)
                  }
                  placeholder="Plant name (no spaces)"
                  disabled={createMutation.isPending}
                />
                <p className="text-xs text-muted-foreground">
                  No spaces allowed.
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="create-plant-location">
                  Location (optional)
                </Label>
                <Input
                  id="create-plant-location"
                  value={createLocation}
                  onChange={(e) => setCreateLocation(e.target.value)}
                  placeholder="Location"
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
                    !createOrgId.trim() ||
                    !createName.trim() ||
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
          <div className="flex items-center gap-2">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" className="min-w-[12rem] justify-between">
                  {orgs.find((o) => o.id === selectedOrgId)?.name ??
                    "All organizations"}
                  <ChevronDown className="ml-2 h-4 w-4 opacity-50" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                <DropdownMenuItem
                  onClick={() => {
                    setSelectedOrgId("");
                    setPage(1);
                  }}
                >
                  All organizations
                </DropdownMenuItem>
                {orgs.map((org) => (
                  <DropdownMenuItem
                    key={org.id}
                    onClick={() => {
                      setSelectedOrgId(org.id);
                      setPage(1);
                    }}
                  >
                    {org.name}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          <Button onClick={() => setShowCreate(true)}>Create plant</Button>
        </CardHeader>
        <CardContent>
          {plants.length === 0 ? (
            <p className="py-8 text-center text-muted-foreground">
              No plants yet.
            </p>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="font-medium">Name</TableHead>
                    <TableHead>Organization</TableHead>
                    <TableHead>Location</TableHead>
                    <TableHead className="w-[80px] text-right">
                      Actions
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {plants.map((plant) => (
                    <TableRow key={plant.id}>
                      <TableCell className="font-medium">
                        {plant.name}
                      </TableCell>
                      <TableCell>
                        {orgs.find((o) => o.id === plant.organization_id)
                          ?.name ?? plant.organization_id}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {plant.location ?? "—"}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => startEdit(plant)}
                        >
                          Edit
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
          {total > 0 && (
            <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t pt-4">
              <p className="text-sm text-muted-foreground">
                Showing {start}–{end} of {total}
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                >
                  Previous
                </Button>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="outline"
                      size="sm"
                      className="min-w-[7rem] justify-between"
                      aria-label="Go to page"
                    >
                      Page {page} of {totalPages}
                      <ChevronDown className="ml-1 h-4 w-4 shrink-0 opacity-50" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    align="center"
                    className="max-h-60 overflow-y-auto"
                  >
                    {Array.from({ length: totalPages }, (_, i) => i + 1).map(
                      (p) => (
                        <DropdownMenuItem
                          key={p}
                          onClick={() => setPage(p)}
                          className={p === page ? "bg-accent" : undefined}
                        >
                          Page {p}
                        </DropdownMenuItem>
                      )
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
