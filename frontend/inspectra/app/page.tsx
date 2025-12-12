"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getHealthCheck } from "@/lib/api/client";
import { CheckCircle2, Code, Database, Zap } from "lucide-react";

export default function Home() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["health"],
    queryFn: getHealthCheck,
  });

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-muted/20">
      <div className="container mx-auto px-4 py-16">
        <div className="mx-auto max-w-4xl">
          {/* Header */}
          <div className="mb-12 text-center">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border bg-card px-4 py-2">
              <Zap className="h-4 w-4 text-primary" />
              <span className="text-sm font-medium">Inspectra</span>
            </div>
            <h1 className="mb-4 text-5xl font-bold tracking-tight">
              Welcome to Inspectra
            </h1>
            <p className="mx-auto max-w-2xl text-lg text-muted-foreground">
              This is a placeholder page for Inspectra skeleton setup. The
              application is configured with Next.js, TypeScript, Tailwind CSS,
              TanStack Query, Zod, and shadcn UI components.
            </p>
          </div>

          {/* Status Card */}
          <Card className="mb-8">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Database className="h-5 w-5" />
                API Connection Status
              </CardTitle>
              <CardDescription>
                Backend connection status and configuration
              </CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading && (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                  <span>Checking API connection...</span>
                </div>
              )}
              {error && (
                <div className="flex items-center gap-2 text-destructive">
                  <span>Error: {error.message}</span>
                </div>
              )}
              {data && (
                <div className="space-y-4">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="h-5 w-5 text-green-500" />
                    <span className="font-medium">API Response Received</span>
                    <Badge variant="secondary" className="ml-auto">
                      {data.status}
                    </Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {data.message}
                  </p>
                  <div className="rounded-md bg-muted p-3 text-xs">
                    <code className="text-muted-foreground">
                      Timestamp: {data.timestamp}
                    </code>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Tech Stack Cards */}
          <div className="mb-8 grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-lg">
                  <Code className="h-4 w-4" />
                  Frontend Stack
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  <Badge>Next.js</Badge>
                  <Badge>TypeScript</Badge>
                  <Badge>Tailwind CSS</Badge>
                  <Badge>TanStack Query</Badge>
                  <Badge>Zod</Badge>
                  <Badge>shadcn/ui</Badge>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-lg">
                  <Code className="h-4 w-4" />
                  Testing & Quality
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="secondary">React Testing Library</Badge>
                  <Badge variant="secondary">Cypress</Badge>
                  <Badge variant="secondary">ESLint (Airbnb)</Badge>
                  <Badge variant="secondary">Prettier</Badge>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Backend Integration Note */}
          <Card className="border-dashed">
            <CardHeader>
              <CardTitle className="text-lg">Backend Integration</CardTitle>
              <CardDescription>
                API calls are currently using mock data
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="mb-4 text-sm text-muted-foreground">
                The backend FastAPI server is not ready yet. When it&apos;s
                available, uncomment the fetch call in{" "}
                <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                  lib/api/client.ts
                </code>{" "}
                and use openapi-typescript to generate types from the OpenAPI
                schema.
              </p>
              <div className="rounded-md bg-muted p-3 text-xs">
                <code className="text-muted-foreground">
                  {`// Example: npx openapi-typescript http://localhost:8000/openapi.json -o ./lib/api/types.ts`}
                </code>
              </div>
            </CardContent>
          </Card>

          {/* Action Buttons */}
          <div className="mt-8 flex justify-center gap-4">
            <Button variant="default" size="lg">
              Get Started
            </Button>
            <Button variant="outline" size="lg">
              Documentation
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
