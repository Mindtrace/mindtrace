"use client";

import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getMachineId, getLicenseStatus, activateLicense, validateLicense } from "@/lib/api/license";
import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { FileKey, Copy, CheckCircle, XCircle, AlertCircle } from "lucide-react";

export default function LicensePage() {
  const queryClient = useQueryClient();
  const [licenseFile, setLicenseFile] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [success, setSuccess] = React.useState<string | null>(null);
  const [copied, setCopied] = React.useState(false);

  const { data: machineId } = useQuery({
    queryKey: ["machine-id"],
    queryFn: getMachineId,
  });

  const { data: licenseStatus, isLoading: isLoadingStatus } = useQuery({
    queryKey: ["license-status"],
    queryFn: getLicenseStatus,
    retry: false,
  });

  const { data: validation } = useQuery({
    queryKey: ["license-validation"],
    queryFn: validateLicense,
    retry: false,
  });

  const activateMutation = useMutation({
    mutationFn: (licenseFileContent: string) =>
      activateLicense({ license_file: licenseFileContent }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["license-status"] });
      queryClient.invalidateQueries({ queryKey: ["license-validation"] });
      setLicenseFile("");
      setSuccess("License activated successfully");
      setTimeout(() => setSuccess(null), 5000);
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setError(
          typeof err.detail === "string"
            ? err.detail
            : "Failed to activate license"
        );
      } else {
        setError("An unexpected error occurred");
      }
    },
  });

  const handleCopyMachineId = async () => {
    if (machineId?.machine_id) {
      await navigator.clipboard.writeText(machineId.machine_id);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleActivate = () => {
    setError(null);
    if (!licenseFile.trim()) {
      setError("Please paste a license file");
      return;
    }
    activateMutation.mutate(licenseFile.trim());
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "valid":
        return <CheckCircle className="h-5 w-5 text-green-500" />;
      case "expired":
        return <XCircle className="h-5 w-5 text-red-500" />;
      case "not_activated":
        return <AlertCircle className="h-5 w-5 text-yellow-500" />;
      default:
        return <XCircle className="h-5 w-5 text-red-500" />;
    }
  };

  const getStatusBadgeVariant = (status: string) => {
    switch (status) {
      case "valid":
        return "default" as const;
      case "expired":
        return "destructive" as const;
      default:
        return "secondary" as const;
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">License</h1>
        <p className="text-muted-foreground">
          Manage your Inspectra license
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Machine ID */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileKey className="h-5 w-5" />
              Machine ID
            </CardTitle>
            <CardDescription>
              Your unique hardware identifier for license binding
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <code className="flex-1 p-3 bg-muted rounded-md font-mono text-sm break-all">
                {machineId?.machine_id || "Loading..."}
              </code>
              <Button
                variant="outline"
                size="icon"
                onClick={handleCopyMachineId}
                disabled={!machineId?.machine_id}
              >
                {copied ? (
                  <CheckCircle className="h-4 w-4 text-green-500" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              Provide this ID when requesting a license
            </p>
          </CardContent>
        </Card>

        {/* License Status */}
        <Card>
          <CardHeader>
            <CardTitle>License Status</CardTitle>
            <CardDescription>Current license information</CardDescription>
          </CardHeader>
          <CardContent>
            {isLoadingStatus ? (
              <p className="text-muted-foreground">Loading...</p>
            ) : licenseStatus ? (
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  {getStatusIcon(licenseStatus.status)}
                  <Badge variant={getStatusBadgeVariant(licenseStatus.status)}>
                    {licenseStatus.status}
                  </Badge>
                </div>
                <div className="grid gap-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Type:</span>
                    <Badge variant="outline">{licenseStatus.license_type}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Expires:</span>
                    <span>
                      {new Date(licenseStatus.expires_at).toLocaleDateString()}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Days Remaining:</span>
                    <span
                      className={
                        licenseStatus.days_remaining < 30
                          ? "text-yellow-500"
                          : ""
                      }
                    >
                      {licenseStatus.days_remaining}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Max Users:</span>
                    <span>{licenseStatus.max_users}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Max Plants:</span>
                    <span>{licenseStatus.max_plants}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Max Lines:</span>
                    <span>{licenseStatus.max_lines}</span>
                  </div>
                </div>
                {licenseStatus.features?.length > 0 && (
                  <div>
                    <p className="text-sm text-muted-foreground mb-2">
                      Features:
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {licenseStatus.features.map((feature) => (
                        <Badge key={feature} variant="outline">
                          {feature}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-2 text-yellow-500">
                <AlertCircle className="h-5 w-5" />
                <span>No license activated</span>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Activate License */}
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>Activate License</CardTitle>
            <CardDescription>
              Paste your license file content (base64 encoded) to activate
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
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
            <div className="space-y-2">
              <Label htmlFor="license-file">License File</Label>
              <Textarea
                id="license-file"
                value={licenseFile}
                onChange={(e) => setLicenseFile(e.target.value)}
                placeholder="Paste your base64-encoded license file content here..."
                rows={6}
                className="font-mono text-sm"
              />
            </div>
            <Button
              onClick={handleActivate}
              disabled={activateMutation.isPending || !licenseFile.trim()}
            >
              {activateMutation.isPending ? "Activating..." : "Activate License"}
            </Button>
          </CardContent>
        </Card>

        {/* Validation Info */}
        {validation && (
          <Card className="md:col-span-2">
            <CardHeader>
              <CardTitle>Validation Result</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2">
                {validation.is_valid ? (
                  <CheckCircle className="h-5 w-5 text-green-500" />
                ) : (
                  <XCircle className="h-5 w-5 text-red-500" />
                )}
                <span>{validation.message}</span>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
