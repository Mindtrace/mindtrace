"use client";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ChevronDown } from "lucide-react";

export type HealthStatusValue = "unknown" | "healthy" | "unhealthy" | "degraded";

const DEFAULT_OPTIONS: readonly HealthStatusValue[] = [
  "unknown",
  "healthy",
  "unhealthy",
  "degraded",
] as const;

export interface HealthStatusDropdownProps {
  id?: string;
  value: HealthStatusValue | "";
  onValueChange: (value: HealthStatusValue) => void;
  disabled?: boolean;
  options?: readonly HealthStatusValue[];
  placeholder?: string;
}

export function HealthStatusDropdown({
  id,
  value,
  onValueChange,
  disabled,
  options = DEFAULT_OPTIONS,
  placeholder = "Select…",
}: HealthStatusDropdownProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          className="w-full justify-between font-normal capitalize"
          disabled={disabled}
          aria-label="Select health status"
        >
          {value || placeholder}
          <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {options.map((s) => (
          <DropdownMenuItem
            key={s}
            onClick={() => onValueChange(s)}
            className={s === value ? "bg-accent capitalize" : "capitalize"}
          >
            {s}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

