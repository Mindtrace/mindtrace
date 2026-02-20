"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import {
  listOrganizations,
  createOrganization,
  updateOrganization,
  getSafeErrorMessage,
  isSessionOrAuthError,
} from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
import type { Organization } from "@/lib/api/types";
import { LoadingOverlay } from "@/components/ui/loading-overlay";

export function OrganizationsPanel() {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [createName, setCreateName] = useState("");
  const [editing, setEditing] = useState<Organization | null>(null);
  const [editName, setEditName] = useState("");
  const [editActive, setEditActive] = useState(true);
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const orgDialogOpen = showCreate || editing !== null;

  /** Organization names must not contain spaces. */
  function hasNoSpaces(s: string): boolean {
    return !/\s/.test(s);
  }

  function handleNameChange(setter: (v: string) => void, value: string) {
    setter(value.replace(/\s/g, ""));
  }

  const { data, isLoading, error } = useQuery({
    queryKey: ["organizations", page],
    queryFn: () =>
      listOrganizations({
        skip: (page - 1) * pageSize,
        limit: pageSize,
      }),
  });

  const createMutation = useMutation({
    mutationFn: (name: string) => createOrganization(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["organizations"] });
      setCreateName("");
      toast.success("Organization created successfully.");
      setShowCreate(false);
    },
    onError: (error: Error) => {
      if (!isSessionOrAuthError(error)) {
        toast.error(
          getSafeErrorMessage(error, "Failed to create organization.")
        );
      }
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      name,
      is_active,
    }: {
      id: string;
      name?: string;
      is_active?: boolean;
    }) => updateOrganization(id, { name, is_active }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["organizations"] });
      toast.success("Organization updated successfully.");
      setEditing(null);
    },
    onError: (error: Error) => {
      if (!isSessionOrAuthError(error)) {
        toast.error(
          getSafeErrorMessage(error, "Failed to update organization.")
        );
      }
    },
  });

  function closeOrgDialog() {
    setShowCreate(false);
    setEditing(null);
  }

  function startEdit(org: Organization) {
    setEditing(org);
    setEditName(org.name);
    setEditActive(org.is_active);
  }

  if (isLoading) {
    return <LoadingOverlay />;
  }
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

  const orgs = data?.items ?? [];
  const totalOrgs = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalOrgs / pageSize));
  const start = totalOrgs === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, totalOrgs);
  const isEdit = editing !== null;

  return (
    <div className="space-y-6">
      <Dialog
        open={orgDialogOpen}
        onOpenChange={(open) => !open && closeOrgDialog()}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {isEdit ? "Edit organization" : "Create organization"}
            </DialogTitle>
            <DialogDescription>
              {isEdit
                ? "Update the organization name or active status."
                : "Add a new organization. Enter a name."}
            </DialogDescription>
          </DialogHeader>

          {isEdit && editing ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const name = editName.trim() || undefined;
                if (name !== undefined && !hasNoSpaces(name)) {
                  toast.error("Organization name cannot contain spaces.");
                  return;
                }
                updateMutation.mutate({
                  id: editing.id,
                  name,
                  is_active: editActive,
                });
              }}
              className="space-y-4"
            >
              <div className="space-y-2">
                <Label htmlFor="edit-org-name">Name</Label>
                <Input
                  id="edit-org-name"
                  value={editName}
                  onChange={(e) =>
                    handleNameChange(setEditName, e.target.value)
                  }
                  placeholder="Organization name (no spaces)"
                  disabled={updateMutation.isPending}
                />
                <p className="text-xs text-muted-foreground">
                  No spaces allowed.
                </p>
              </div>
              <label className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={editActive}
                  onChange={(e) => setEditActive(e.target.checked)}
                  disabled={updateMutation.isPending}
                />
                <span className="text-sm">Active</span>
              </label>
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={closeOrgDialog}
                >
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
                if (!name || !hasNoSpaces(name)) {
                  if (name && !hasNoSpaces(name)) {
                    toast.error("Organization name cannot contain spaces.");
                  }
                  return;
                }
                if (!createMutation.isPending) {
                  createMutation.mutate(name);
                }
              }}
              className="space-y-4"
            >
              <div className="space-y-2">
                <Label htmlFor="create-org-name">Name</Label>
                <Input
                  id="create-org-name"
                  value={createName}
                  onChange={(e) =>
                    handleNameChange(setCreateName, e.target.value)
                  }
                  placeholder="Organization name (no spaces)"
                  disabled={createMutation.isPending}
                />
                <p className="text-xs text-muted-foreground">
                  No spaces allowed.
                </p>
              </div>
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={closeOrgDialog}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={!createName.trim() || createMutation.isPending}
                >
                  {createMutation.isPending ? "Creating…" : "Create"}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>

      <Card>
        <CardHeader className="flex flex-row items-center justify-end py-4">
          <Button onClick={() => setShowCreate(true)}>
            Create organization
          </Button>
        </CardHeader>
        <CardContent>
          {orgs.length === 0 ? (
            <p className="py-8 text-center text-muted-foreground">
              No organizations yet.
            </p>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="font-medium">Name</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="w-[80px] text-right">
                      Actions
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {orgs.map((org) => (
                    <TableRow key={org.id}>
                      <TableCell className="font-medium">{org.name}</TableCell>
                      <TableCell>
                        {org.is_active ? (
                          <Badge variant="secondary" className="font-normal">
                            Active
                          </Badge>
                        ) : (
                          <Badge variant="outline">Inactive</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => startEdit(org)}
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
          {totalOrgs > 0 && (
            <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t pt-4">
              <p className="text-sm text-muted-foreground">
                Showing {start}–{end} of {totalOrgs}
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
