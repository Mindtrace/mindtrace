"use client";

import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/components/providers/auth-provider";
import { listUsers } from "@/lib/api/users";
import { listRoles } from "@/lib/api/roles";
import { getLicenseStatus } from "@/lib/api/license";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Users, Shield, FileKey } from "lucide-react";

export default function DashboardPage() {
  const { user } = useAuth();

  const { data: usersData } = useQuery({
    queryKey: ["users", { page: 1, page_size: 1 }],
    queryFn: () => listUsers({ page: 1, page_size: 1 }),
  });

  const { data: rolesData } = useQuery({
    queryKey: ["roles"],
    queryFn: listRoles,
  });

  const { data: licenseData } = useQuery({
    queryKey: ["license-status"],
    queryFn: getLicenseStatus,
    retry: false,
  });

  return (
    <div className="space-y-6">
      {/* Welcome */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">
          Welcome back, {user?.email}
        </h1>
        <p className="text-muted-foreground">
          Here&apos;s an overview of your Inspectra instance.
        </p>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Users</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {usersData?.total ?? "..."}
            </div>
            <p className="text-xs text-muted-foreground">
              Registered users in the system
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Roles</CardTitle>
            <Shield className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {rolesData?.total ?? "..."}
            </div>
            <p className="text-xs text-muted-foreground">
              Configured access roles
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">License</CardTitle>
            <FileKey className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              {licenseData ? (
                <>
                  <Badge
                    variant={
                      licenseData.status === "valid" ? "default" : "destructive"
                    }
                  >
                    {licenseData.status}
                  </Badge>
                  {licenseData.days_remaining !== undefined && (
                    <span className="text-sm text-muted-foreground">
                      {licenseData.days_remaining} days left
                    </span>
                  )}
                </>
              ) : (
                <Badge variant="secondary">Not activated</Badge>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {licenseData?.license_type || "No license"}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Quick actions */}
      <Card>
        <CardHeader>
          <CardTitle>Quick Actions</CardTitle>
          <CardDescription>
            Common tasks you can perform
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-4">
            <a
              href="/dashboard/users/new"
              className="flex items-center gap-2 rounded-md border p-3 hover:bg-muted transition-colors"
            >
              <Users className="h-4 w-4" />
              <span className="text-sm">Add User</span>
            </a>
            <a
              href="/dashboard/roles"
              className="flex items-center gap-2 rounded-md border p-3 hover:bg-muted transition-colors"
            >
              <Shield className="h-4 w-4" />
              <span className="text-sm">Manage Roles</span>
            </a>
            <a
              href="/dashboard/settings/password-policies"
              className="flex items-center gap-2 rounded-md border p-3 hover:bg-muted transition-colors"
            >
              <Shield className="h-4 w-4" />
              <span className="text-sm">Password Policies</span>
            </a>
            <a
              href="/dashboard/settings/license"
              className="flex items-center gap-2 rounded-md border p-3 hover:bg-muted transition-colors"
            >
              <FileKey className="h-4 w-4" />
              <span className="text-sm">License Settings</span>
            </a>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
