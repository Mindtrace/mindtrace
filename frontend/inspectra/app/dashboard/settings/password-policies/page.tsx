"use client";

import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listPasswordPolicies,
  createPasswordPolicy,
  updatePasswordPolicy,
  deletePasswordPolicy,
} from "@/lib/api/password-policies";
import type { PasswordPolicy, PasswordPolicyCreateRequest } from "@/lib/api/types";
import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
  DialogTrigger,
} from "@/components/ui/dialog";
import { Plus, Edit, Trash2, Star } from "lucide-react";

export default function PasswordPoliciesPage() {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [editingPolicy, setEditingPolicy] = React.useState<PasswordPolicy | null>(null);
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [isDefault, setIsDefault] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const { data: policiesData, isLoading } = useQuery({
    queryKey: ["password-policies"],
    queryFn: listPasswordPolicies,
  });

  const createMutation = useMutation({
    mutationFn: (data: PasswordPolicyCreateRequest) => createPasswordPolicy(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["password-policies"] });
      resetForm();
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setError(typeof err.detail === "string" ? err.detail : "Failed to create policy");
      }
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<PasswordPolicyCreateRequest> }) =>
      updatePasswordPolicy(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["password-policies"] });
      resetForm();
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setError(typeof err.detail === "string" ? err.detail : "Failed to update policy");
      }
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deletePasswordPolicy,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["password-policies"] });
    },
  });

  const resetForm = () => {
    setDialogOpen(false);
    setEditingPolicy(null);
    setName("");
    setDescription("");
    setIsDefault(false);
    setError(null);
  };

  const openCreateDialog = () => {
    resetForm();
    setDialogOpen(true);
  };

  const openEditDialog = (policy: PasswordPolicy) => {
    setEditingPolicy(policy);
    setName(policy.name);
    setDescription(policy.description || "");
    setIsDefault(policy.is_default);
    setError(null);
    setDialogOpen(true);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (editingPolicy) {
      updateMutation.mutate({
        id: editingPolicy.id,
        data: {
          name,
          description: description || undefined,
          is_default: isDefault,
        },
      });
    } else {
      createMutation.mutate({
        name,
        description: description || undefined,
        is_default: isDefault,
      });
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Password Policies</h1>
          <p className="text-muted-foreground">
            Configure password requirements for user accounts
          </p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button onClick={openCreateDialog}>
              <Plus className="mr-2 h-4 w-4" />
              Add Policy
            </Button>
          </DialogTrigger>
          <DialogContent>
            <form onSubmit={handleSubmit}>
              <DialogHeader>
                <DialogTitle>
                  {editingPolicy ? "Edit Policy" : "Create Policy"}
                </DialogTitle>
                <DialogDescription>
                  {editingPolicy
                    ? "Update the password policy"
                    : "Add a new password policy"}
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-4">
                {error && (
                  <div className="p-3 text-sm text-red-500 bg-red-50 dark:bg-red-950 rounded-md">
                    {error}
                  </div>
                )}
                <div className="space-y-2">
                  <Label htmlFor="name">Name</Label>
                  <Input
                    id="name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                    placeholder="e.g., Standard Policy"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="description">Description</Label>
                  <Textarea
                    id="description"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Describe this policy"
                    rows={3}
                  />
                </div>
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="is_default"
                    checked={isDefault}
                    onCheckedChange={(checked) => setIsDefault(checked)}
                  />
                  <Label htmlFor="is_default" className="cursor-pointer">
                    Set as default policy
                  </Label>
                </div>
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={resetForm}>
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={createMutation.isPending || updateMutation.isPending}
                >
                  {createMutation.isPending || updateMutation.isPending
                    ? "Saving..."
                    : editingPolicy
                    ? "Update Policy"
                    : "Create Policy"}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>All Policies</CardTitle>
          <CardDescription>
            {policiesData?.total ?? 0} password policies configured
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="text-center py-8 text-muted-foreground">
              Loading...
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead>Rules</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-[100px]"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {policiesData?.items.map((policy) => (
                  <TableRow key={policy.id}>
                    <TableCell className="font-medium">
                      <div className="flex items-center gap-2">
                        {policy.name}
                        {policy.is_default && (
                          <Star className="h-4 w-4 text-yellow-500 fill-yellow-500" />
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {policy.description || "-"}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {policy.rules?.length || 0} rules
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={policy.is_active ? "default" : "secondary"}>
                        {policy.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openEditDialog(policy)}
                        >
                          <Edit className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            if (confirm("Are you sure you want to delete this policy?")) {
                              deleteMutation.mutate(policy.id);
                            }
                          }}
                          disabled={policy.is_default}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {policiesData?.items.length === 0 && (
                  <TableRow>
                    <TableCell
                      colSpan={5}
                      className="text-center text-muted-foreground"
                    >
                      No password policies found
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Policy Rules Info */}
      <Card>
        <CardHeader>
          <CardTitle>About Password Rules</CardTitle>
          <CardDescription>
            Available rule types for password policies
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
            {[
              { type: "min_length", desc: "Minimum password length" },
              { type: "max_length", desc: "Maximum password length" },
              { type: "require_uppercase", desc: "Require uppercase letters" },
              { type: "require_lowercase", desc: "Require lowercase letters" },
              { type: "require_digit", desc: "Require numbers" },
              { type: "require_special", desc: "Require special characters" },
              { type: "no_repeating_chars", desc: "Disallow repeated characters" },
              { type: "disallow_common", desc: "Disallow common passwords" },
            ].map((rule) => (
              <div
                key={rule.type}
                className="flex items-center gap-2 p-2 rounded-md border"
              >
                <Badge variant="outline" className="font-mono text-xs">
                  {rule.type}
                </Badge>
                <span className="text-sm text-muted-foreground">
                  {rule.desc}
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
