"use client";

import { ChevronDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export type OutlineDropdownSelectItem = { id: string; label: string };

type OutlineDropdownSelectProps = {
  id: string;
  label: string;
  value: string;
  onValueChange: (next: string) => void;
  placeholder: string;
  items: OutlineDropdownSelectItem[];
  className?: string;
};

export function OutlineDropdownSelect({
  id,
  label,
  value,
  onValueChange,
  placeholder,
  items,
  className,
}: OutlineDropdownSelectProps) {
  const selected = items.find((x) => x.id === value);
  const display =
    value && selected ? selected.label : value ? value : placeholder;

  return (
    <div className={cn("space-y-2", className)}>
      <Label htmlFor={id}>{label}</Label>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            id={id}
            variant="outline"
            className="w-full justify-between font-normal"
          >
            <span className="min-w-0 flex-1 truncate text-left">{display}</span>
            <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="start"
          className="w-[var(--radix-dropdown-menu-trigger-width)] max-h-[min(320px,70vh)] overflow-y-auto"
        >
          <DropdownMenuItem onClick={() => onValueChange("")}>
            {placeholder}
          </DropdownMenuItem>
          {items.map((item) => (
            <DropdownMenuItem
              key={item.id}
              onClick={() => onValueChange(item.id)}
            >
              {item.label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
