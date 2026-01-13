"use client";

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getUser, updateUser, resetUserPassword, activateUser, deactivateUser } from "@/lib/api/users";
import { listRoles } from "@/lib/api/roles";
import { validatePassword } from "@/lib/api/password-policies";
import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectOption } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ArrowLeft, Key, UserCheck, UserX } from "lucide-react";
import Link from "next/link";

export default function UserDetailPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const userId = params.id as string;

  const [roleId, setRoleId] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [success, setSuccess] = React.useState<string | null>(null);

  // Reset password dialog
  const [resetDialogOpen, setResetDialogOpen] = React.useState(false);
  const [newPassword, setNewPassword] = React.useState("");
  const [passwordErrors, setPasswordErrors] = React.useState<string[]>([]);

  const { data: user, isLoading } = useQuery({
    queryKey: ["user", userId],
    queryFn: () => getUser(userId),
  });

  const { data: rolesData } = useQuery({
    queryKey: ["roles"],
    queryFn: listRoles,
  });

  // Set initial role when user loads
  React.useEffect(() => {
    if (user) {
      setRoleId(user.role_id);
    }
  }, [user]);

  const updateMutation = useMutation({
    mutationFn: (data: { role_id?: string }) => updateUser(userId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["user", userId] });
      setSuccess("User updated successfully");
      setTimeout(() => setSuccess(null), 3000);
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setError(typeof err.detail === "string" ? err.detail : "Failed to update user");
      }
    },
  });

  const resetPasswordMutation = useMutation({
    mutationFn: (newPassword: string) =>
      resetUserPassword(userId, { new_password: newPassword }),
    onSuccess: () => {
      setResetDialogOpen(false);
      setNewPassword("");
      setPasswordErrors([]);
      setSuccess("Password reset successfully");
      setTimeout(() => setSuccess(null), 3000);
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setError(typeof err.detail === "string" ? err.detail : "Failed to reset password");
      }
    },
  });

  const activateMutation = useMutation({
    mutationFn: () => activateUser(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["user", userId] });
      setSuccess("User activated");
      setTimeout(() => setSuccess(null), 3000);
    },
  });

  const deactivateMutation = useMutation({
    mutationFn: () => deactivateUser(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["user", userId] });
      setSuccess("User deactivated");
      setTimeout(() => setSuccess(null), 3000);
    },
  });

  const handleUpdateRole = () => {
    if (roleId !== user?.role_id) {
      updateMutation.mutate({ role_id: roleId });
    }
  };

  const handleResetPassword = async () => {
    // Validate password first
    try {
      const result = await validatePassword(newPassword);
      if (!result.is_valid) {
        setPasswordErrors(result.errors);
        return;
      }
    } catch {
      // Continue anyway if validation service is unavailable
    }

    resetPasswordMutation.mutate(newPassword);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="flex items-center justify-center py-8">
        <p className="text-muted-foreground">User not found</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/dashboard/users">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
        </Link>
        <div className="flex-1">
          <h1 className="text-3xl font-bold tracking-tight">{user.email}</h1>
          <p className="text-muted-foreground">Manage user settings</p>
        </div>
        <Badge variant={user.is_active ? "default" : "secondary"}>
          {user.is_active ? "Active" : "Inactive"}
        </Badge>
      </div>

      {error && (
        <div className="p-3 text-sm text-red-500 bg-red-50 dark:bg-red-950 rounded-md">
          {error}
        </div>
      )}

      {success && (
        <div className="p-3 text-sm text-green-500 bg-green-50 dark:bg-green-950 rounded-md">
          {success}
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        {/* User Info */}
        <Card>
          <CardHeader>
            <CardTitle>User Information</CardTitle>
            <CardDescription>Basic user details</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label className="text-muted-foreground">Email</Label>
              <p className="font-medium">{user.email}</p>
            </div>
            <div>
              <Label className="text-muted-foreground">User ID</Label>
              <p className="font-mono text-sm">{user.id}</p>
            </div>
          </CardContent>
        </Card>

        {/* Role */}
        <Card>
          <CardHeader>
            <CardTitle>Role Assignment</CardTitle>
            <CardDescription>Change the user&apos;s role</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="role">Role</Label>
              <Select
                id="role"
                value={roleId}
                onChange={(e) => setRoleId(e.target.value)}
              >
                {rolesData?.items.map((role) => (
                  <SelectOption key={role.id} value={role.id}>
                    {role.name}
                  </SelectOption>
                ))}
              </Select>
            </div>
            <Button
              onClick={handleUpdateRole}
              disabled={updateMutation.isPending || roleId === user.role_id}
            >
              {updateMutation.isPending ? "Saving..." : "Save Changes"}
            </Button>
          </CardContent>
        </Card>

        {/* Actions */}
        <Card>
          <CardHeader>
            <CardTitle>Actions</CardTitle>
            <CardDescription>Manage user account</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Reset Password */}
            <Dialog open={resetDialogOpen} onOpenChange={setResetDialogOpen}>
              <DialogTrigger asChild>
                <Button variant="outline" className="w-full justify-start">
                  <Key className="mr-2 h-4 w-4" />
                  Reset Password
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Reset Password</DialogTitle>
                  <DialogDescription>
                    Set a new password for {user.email}
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-4">
                  <div className="space-y-2">
                    <Label htmlFor="new-password">New Password</Label>
                    <Input
                      id="new-password"
                      type="password"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      placeholder="Enter new password"
                    />
                    {passwordErrors.length > 0 && (
                      <ul className="text-sm text-red-500 list-disc list-inside">
                        {passwordErrors.map((err, i) => (
                          <li key={i}>{err}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
                <DialogFooter>
                  <Button
                    variant="outline"
                    onClick={() => setResetDialogOpen(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    onClick={handleResetPassword}
                    disabled={!newPassword || resetPasswordMutation.isPending}
                  >
                    {resetPasswordMutation.isPending
                      ? "Resetting..."
                      : "Reset Password"}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>

            {/* Activate/Deactivate */}
            {user.is_active ? (
              <Button
                variant="outline"
                className="w-full justify-start"
                onClick={() => deactivateMutation.mutate()}
                disabled={deactivateMutation.isPending}
              >
                <UserX className="mr-2 h-4 w-4" />
                {deactivateMutation.isPending ? "Deactivating..." : "Deactivate User"}
              </Button>
            ) : (
              <Button
                variant="outline"
                className="w-full justify-start"
                onClick={() => activateMutation.mutate()}
                disabled={activateMutation.isPending}
              >
                <UserCheck className="mr-2 h-4 w-4" />
                {activateMutation.isPending ? "Activating..." : "Activate User"}
              </Button>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
