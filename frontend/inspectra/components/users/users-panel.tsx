"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useMemo } from "react";
import { toast } from "sonner";
import {
  listUsers,
  createUser,
  updateUser,
  listOrganizations,
  getSafeErrorMessage,
  isSessionOrAuthError,
} from "@/lib/api/client";
import { useAuth } from "@/context/auth-context";
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
import { ChevronDown, Search } from "lucide-react";
import type { User, UserRole } from "@/lib/api/types";
import { LoadingOverlay } from "@/components/ui/loading-overlay";

const ROLES: UserRole[] = [
  "super_admin",
  "admin",
  "user",
  "plant_manager",
  "line_manager",
  "qc",
  "ceo",
  "mt_user",
];

const selectClassName =
  "flex h-9 w-full cursor-pointer rounded-md border border-input bg-transparent px-3 py-1 text-sm";

export function UsersPanel() {
  const queryClient = useQueryClient();
  const { user: me } = useAuth();
  const isSuperAdmin = me?.role === "super_admin";
  const canManageUsers = isSuperAdmin || me?.role === "admin";

  const [showCreate, setShowCreate] = useState(false);
  const [createEmail, setCreateEmail] = useState("");
  const [createPassword, setCreatePassword] = useState("");
  const [createRole, setCreateRole] = useState<UserRole>("user");
  const [createOrgId, setCreateOrgId] = useState("");
  const [createFirstName, setCreateFirstName] = useState("");
  const [createLastName, setCreateLastName] = useState("");

  const [editing, setEditing] = useState<User | null>(null);
  const [editFirstName, setEditFirstName] = useState("");
  const [editLastName, setEditLastName] = useState("");
  const [editRole, setEditRole] = useState<UserRole>("user");
  const [editStatus, setEditStatus] = useState<"active" | "inactive">("active");

  const [selectedOrgId, setSelectedOrgId] = useState("");
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const [submittedSearch, setSubmittedSearch] = useState("");
  const pageSize = 10;

  const userDialogOpen = showCreate || editing !== null;

  function handleSearchSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmittedSearch(searchInput.trim());
    setPage(1);
  }

  const {
    data: usersData,
    isLoading: usersLoading,
    error: usersError,
  } = useQuery({
    queryKey: [
      "users",
      isSuperAdmin ? selectedOrgId : "org",
      page,
      submittedSearch,
    ],
    queryFn: () =>
      listUsers(isSuperAdmin && selectedOrgId ? selectedOrgId : undefined, {
        skip: (page - 1) * pageSize,
        limit: pageSize,
        search: submittedSearch || undefined,
      }),
  });
  const { data: orgsData } = useQuery({
    queryKey: ["organizations"],
    queryFn: () => listOrganizations({ limit: 500 }),
    enabled: isSuperAdmin,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createUser({
        email: createEmail.trim(),
        password: createPassword,
        role: createRole,
        organization_id: isSuperAdmin
          ? effectiveCreateOrgId
          : me!.organization_id,
        first_name: createFirstName.trim(),
        last_name: createLastName.trim(),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      toast.success("User created successfully.");
      closeUserDialog();
      setCreateEmail("");
      setCreatePassword("");
      setCreateFirstName("");
      setCreateLastName("");
    },
    onError: (error: Error) => {
      if (!isSessionOrAuthError(error)) {
        toast.error(getSafeErrorMessage(error, "Failed to create user."));
      }
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      ...payload
    }: {
      id: string;
      first_name?: string;
      last_name?: string;
      role?: UserRole;
      status?: "active" | "inactive";
    }) => updateUser(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      toast.success("User updated successfully.");
      closeUserDialog();
    },
    onError: (error: Error) => {
      if (!isSessionOrAuthError(error)) {
        toast.error(getSafeErrorMessage(error, "Failed to update user."));
      }
    },
  });

  function closeUserDialog() {
    setShowCreate(false);
    setEditing(null);
  }

  function startEdit(u: User) {
    setEditing(u);
    setEditFirstName(u.first_name);
    setEditLastName(u.last_name);
    setEditRole(u.role);
    setEditStatus(u.status as "active" | "inactive");
  }

  const users = usersData?.items ?? [];
  const totalUsers = usersData?.total ?? 0;
  const orgs = useMemo(() => orgsData?.items ?? [], [orgsData?.items]);
  const effectiveCreateOrgId = createOrgId || orgs[0]?.id || "";
  const totalPages = Math.max(1, Math.ceil(totalUsers / pageSize));
  const start = totalUsers === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, totalUsers);

  if (usersLoading) {
    return <LoadingOverlay />;
  }
  if (usersError) {
    return (
      <Card>
        <CardContent className="pt-6">
          <p className="text-destructive">{usersError.message}</p>
        </CardContent>
      </Card>
    );
  }

  const roleOptions = isSuperAdmin
    ? ROLES
    : ROLES.filter((r) => r !== "super_admin");
  const isEdit = editing !== null;

  return (
    <div className="space-y-6">
      <Dialog
        open={userDialogOpen}
        onOpenChange={(open) => !open && closeUserDialog()}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{isEdit ? "Edit user" : "Add user"}</DialogTitle>
            <DialogDescription>
              {isEdit
                ? "Update name, role, or status."
                : "Create a new user. Fill in all required fields."}
            </DialogDescription>
          </DialogHeader>

          {isEdit && editing ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                updateMutation.mutate({
                  id: editing.id,
                  first_name: editFirstName.trim() || undefined,
                  last_name: editLastName.trim() || undefined,
                  role: editRole,
                  status: editStatus,
                });
              }}
              className="space-y-4"
            >
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="edit-first-name">First name</Label>
                  <Input
                    id="edit-first-name"
                    value={editFirstName}
                    onChange={(e) => setEditFirstName(e.target.value)}
                    disabled={updateMutation.isPending}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="edit-last-name">Last name</Label>
                  <Input
                    id="edit-last-name"
                    value={editLastName}
                    onChange={(e) => setEditLastName(e.target.value)}
                    disabled={updateMutation.isPending}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-role">Role</Label>
                <select
                  id="edit-role"
                  className={selectClassName}
                  value={editRole}
                  onChange={(e) => setEditRole(e.target.value as UserRole)}
                  disabled={updateMutation.isPending}
                >
                  {(me?.role === "admin" ? roleOptions : ROLES).map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-status">Status</Label>
                <select
                  id="edit-status"
                  className={selectClassName}
                  value={editStatus}
                  onChange={(e) =>
                    setEditStatus(e.target.value as "active" | "inactive")
                  }
                  disabled={updateMutation.isPending}
                >
                  <option value="active">active</option>
                  <option value="inactive">inactive</option>
                </select>
              </div>
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={closeUserDialog}
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
                if (
                  createEmail.trim() &&
                  createPassword &&
                  createFirstName.trim() &&
                  createLastName.trim() &&
                  (!isSuperAdmin || effectiveCreateOrgId) &&
                  !createMutation.isPending
                ) {
                  createMutation.mutate();
                }
              }}
              className="space-y-4"
            >
              {createMutation.isError && (
                <p
                  className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
                  role="alert"
                >
                  {(() => {
                    const err = createMutation.error;
                    const raw = err instanceof Error ? err.message : "";
                    const allowed =
                      raw.includes("Email already registered") ||
                      raw.includes("Invalid request") ||
                      raw.includes("Password does not meet");
                    return getSafeErrorMessage(
                      err,
                      allowed ? raw : "Something went wrong. Please try again."
                    );
                  })()}
                </p>
              )}
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="create-email">Email</Label>
                  <Input
                    id="create-email"
                    type="email"
                    value={createEmail}
                    onChange={(e) => setCreateEmail(e.target.value)}
                    placeholder="user@example.com"
                    disabled={createMutation.isPending}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="create-password">Password</Label>
                  <Input
                    id="create-password"
                    type="password"
                    value={createPassword}
                    onChange={(e) => setCreatePassword(e.target.value)}
                    placeholder="••••••••"
                    disabled={createMutation.isPending}
                  />
                </div>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="create-first-name">First name</Label>
                  <Input
                    id="create-first-name"
                    value={createFirstName}
                    onChange={(e) => setCreateFirstName(e.target.value)}
                    disabled={createMutation.isPending}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="create-last-name">Last name</Label>
                  <Input
                    id="create-last-name"
                    value={createLastName}
                    onChange={(e) => setCreateLastName(e.target.value)}
                    disabled={createMutation.isPending}
                  />
                </div>
              </div>
              {isSuperAdmin && (
                <div className="space-y-2">
                  <Label htmlFor="create-org">Organization</Label>
                  <select
                    id="create-org"
                    className={selectClassName}
                    value={effectiveCreateOrgId}
                    onChange={(e) => setCreateOrgId(e.target.value)}
                    disabled={createMutation.isPending}
                  >
                    {orgs.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              <div className="space-y-2">
                <Label htmlFor="create-role">Role</Label>
                <select
                  id="create-role"
                  className={selectClassName}
                  value={createRole}
                  onChange={(e) => setCreateRole(e.target.value as UserRole)}
                  disabled={createMutation.isPending}
                >
                  {roleOptions.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </div>
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={closeUserDialog}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={
                    !createEmail.trim() ||
                    !createPassword ||
                    !createFirstName.trim() ||
                    !createLastName.trim() ||
                    (isSuperAdmin && !effectiveCreateOrgId) ||
                    createMutation.isPending
                  }
                >
                  {createMutation.isPending ? "Creating…" : "Create user"}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>

      <Card>
        <CardHeader className="flex flex-col gap-3 py-4 sm:grid sm:grid-cols-2 sm:gap-3 md:flex md:flex-row md:items-center md:justify-between md:gap-2">
          {canManageUsers && (
            <div className="flex w-full justify-end sm:col-start-2 md:order-3 md:w-auto">
              <Button onClick={() => setShowCreate(true)}>Add user</Button>
            </div>
          )}
          <div
            className={`flex w-full min-w-0 items-center gap-2 sm:col-start-1 md:order-1 md:w-auto ${canManageUsers ? "sm:row-start-2" : ""}`}
          >
            {isSuperAdmin && orgs.length > 0 && (
              <>
                <Label
                  htmlFor="filter-org"
                  className="shrink-0 text-sm text-muted-foreground whitespace-nowrap"
                >
                  Organization
                </Label>
                <select
                  id="filter-org"
                  className={
                    selectClassName +
                    " min-w-0 flex-1 sm:min-w-[10rem] sm:flex-none"
                  }
                  value={selectedOrgId}
                  onChange={(e) => {
                    setSelectedOrgId(e.target.value);
                    setPage(1);
                  }}
                >
                  <option value="">All</option>
                  {orgs.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.name}
                    </option>
                  ))}
                </select>
              </>
            )}
          </div>
          <form
            onSubmit={handleSearchSubmit}
            className={`flex w-full min-w-0 items-center gap-1.5 sm:col-start-2 sm:justify-self-end md:order-2 md:w-auto md:justify-self-auto ${canManageUsers ? "sm:row-start-2" : ""}`}
          >
            <div className="relative min-w-0 flex-1 sm:min-w-[12rem] sm:flex-none">
              <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground pointer-events-none" />
              <Input
                type="search"
                placeholder="Search name or email…"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                className="min-w-0 pl-8"
                aria-label="Search users by first name, last name, or email"
              />
            </div>
            <Button
              type="submit"
              variant="secondary"
              size="sm"
              className="shrink-0"
            >
              Search
            </Button>
          </form>
        </CardHeader>
        <CardContent>
          {users.length === 0 ? (
            <p className="py-8 text-center text-muted-foreground">No users.</p>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="font-medium">First name</TableHead>
                    <TableHead className="font-medium">Last name</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead>Status</TableHead>
                    {canManageUsers && (
                      <TableHead className="w-[80px] text-right">
                        Actions
                      </TableHead>
                    )}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {users.map((u) => (
                    <TableRow key={u.id}>
                      <TableCell className="font-medium">
                        {u.first_name}
                      </TableCell>
                      <TableCell className="font-medium">
                        {u.last_name}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {u.email}
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary">{u.role}</Badge>
                      </TableCell>
                      <TableCell>
                        {u.status === "active" ? (
                          <Badge variant="secondary" className="font-normal">
                            active
                          </Badge>
                        ) : (
                          <Badge variant="outline">inactive</Badge>
                        )}
                      </TableCell>
                      {canManageUsers && (
                        <TableCell className="text-right">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => startEdit(u)}
                          >
                            Edit
                          </Button>
                        </TableCell>
                      )}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
          {totalUsers > 0 && (
            <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t pt-4">
              <p className="text-sm text-muted-foreground">
                Showing {start}–{end} of {totalUsers}
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
