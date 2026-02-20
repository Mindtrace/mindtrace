"use client";

import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const SIDEBAR_WIDTH_KEY = "sidebar-width";
const SIDEBAR_COLLAPSED_KEY = "sidebar-collapsed";
const DEFAULT_WIDTH = 256;
const MIN_WIDTH = 192;
const MAX_WIDTH = 384;
const COLLAPSED_WIDTH = 56;

type SidebarContextValue = {
  state: "expanded" | "collapsed";
  width: number;
  setWidth: (w: number) => void;
  toggleSidebar: () => void;
  ref: React.RefObject<HTMLDivElement | null>;
};

const SidebarContext = React.createContext<SidebarContextValue | null>(null);

function useSidebar() {
  const ctx = React.useContext(SidebarContext);
  if (!ctx) throw new Error("useSidebar must be used within SidebarProvider");
  return ctx;
}

function getStoredWidth(): number {
  if (typeof window === "undefined") return DEFAULT_WIDTH;
  const v = localStorage.getItem(SIDEBAR_WIDTH_KEY);
  if (!v) return DEFAULT_WIDTH;
  const n = parseInt(v, 10);
  return Number.isFinite(n)
    ? Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, n))
    : DEFAULT_WIDTH;
}

const SIDEBAR_MEDIA_QUERY = "(min-width: 768px)";

function getStoredCollapsed(): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
}

const SidebarProvider = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<"div">
>(function SidebarProvider({ className, style, children, ...props }, ref) {
  const [width, setWidthState] = React.useState(DEFAULT_WIDTH);
  const [userCollapsed, setUserCollapsed] = React.useState(false);
  const [isLargeScreen, setIsLargeScreen] = React.useState(false);
  const sidebarRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    setWidthState(getStoredWidth());
    setUserCollapsed(getStoredCollapsed());
    const mql = window.matchMedia(SIDEBAR_MEDIA_QUERY);
    setIsLargeScreen(mql.matches);
    const handleChange = (e: MediaQueryListEvent) => {
      setIsLargeScreen(e.matches);
    };
    mql.addEventListener("change", handleChange);
    return () => mql.removeEventListener("change", handleChange);
  }, []);

  const setWidth = React.useCallback((w: number) => {
    const clamped = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, w));
    setWidthState(clamped);
    if (typeof window !== "undefined") {
      localStorage.setItem(SIDEBAR_WIDTH_KEY, String(clamped));
    }
  }, []);

  const toggleSidebar = React.useCallback(() => {
    const next = !userCollapsed;
    setUserCollapsed(next);
    if (typeof window !== "undefined") {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next));
    }
  }, [userCollapsed]);

  const collapsed = isLargeScreen ? userCollapsed : true;
  const state = collapsed ? "collapsed" : "expanded";
  const currentWidth = collapsed ? COLLAPSED_WIDTH : width;
  const value: SidebarContextValue = {
    state,
    width,
    setWidth,
    toggleSidebar,
    ref: sidebarRef,
  };

  return (
    <SidebarContext.Provider value={value}>
      <TooltipProvider delayDuration={0}>
        <div
          ref={ref}
          className={cn(
            "group group/sidebar grid h-screen w-full overflow-hidden",
            className
          )}
          data-state={state}
          data-collapsible={state}
          style={
            {
              "--sidebar-width": `${width}px`,
              "--sidebar-width-collapsed": `${COLLAPSED_WIDTH}px`,
              "--sidebar-current-width": `${currentWidth}px`,
              gridTemplateColumns: "var(--sidebar-current-width) 1fr",
              gap: 0,
              ...style,
            } as React.CSSProperties
          }
          {...props}
        >
          {children}
        </div>
      </TooltipProvider>
    </SidebarContext.Provider>
  );
});

const Sidebar = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<"div"> & { side?: "left" | "right" }
>(function Sidebar({ side = "left", className, children, ...props }, ref) {
  const { state, width } = useSidebar();
  const currentWidth = state === "collapsed" ? COLLAPSED_WIDTH : width;

  return (
    <div
      ref={ref}
      data-side={side}
      data-slot="sidebar"
      data-state={state}
      className={cn(
        "fixed inset-y-0 z-10 flex h-svh flex-col bg-sidebar text-sidebar-foreground transition-[width] duration-200 ease-linear",
        side === "left"
          ? "left-0 border-r border-sidebar-border"
          : "right-0 border-l border-sidebar-border",
        state === "collapsed" && "overflow-visible",
        className
      )}
      style={{ width: `${currentWidth}px`, minWidth: `${currentWidth}px` }}
      {...props}
    >
      {children}
    </div>
  );
});

const SidebarHeader = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<"div">
>(function SidebarHeader({ className, ...props }, ref) {
  return (
    <div
      ref={ref}
      data-slot="sidebar-header"
      className={cn("flex flex-col gap-2 p-2", className)}
      {...props}
    />
  );
});

const SidebarContent = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<"div">
>(function SidebarContent({ className, children, ...props }, ref) {
  return (
    <div
      ref={ref}
      data-slot="sidebar-content"
      className={cn("flex flex-1 flex-col min-h-0 w-full", className)}
      {...props}
    >
      <div className="h-full min-h-0 w-full overflow-y-auto overflow-x-hidden -mr-[2px]">
        <div className="flex flex-col gap-2 py-2 pl-2">{children}</div>
      </div>
    </div>
  );
});

const SidebarFooter = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<"div">
>(function SidebarFooter({ className, ...props }, ref) {
  return (
    <div
      ref={ref}
      data-slot="sidebar-footer"
      className={cn(
        "flex flex-col gap-2 p-2 border-t border-sidebar-border",
        className
      )}
      {...props}
    />
  );
});

const SidebarGroup = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<"div">
>(function SidebarGroup({ className, ...props }, ref) {
  return (
    <div
      ref={ref}
      data-slot="sidebar-group"
      className={cn("flex flex-col gap-1", className)}
      {...props}
    />
  );
});

const SidebarGroupLabel = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<"div"> & { asChild?: boolean }
>(function SidebarGroupLabel({ asChild = false, className, ...props }, ref) {
  const Comp = asChild ? Slot : "div";
  return (
    <Comp
      ref={ref}
      data-slot="sidebar-group-label"
      className={cn(
        "px-2 py-1.5 text-xs font-medium text-sidebar-foreground/70",
        "group-data-[collapsible=collapsed]:hidden",
        className
      )}
      {...props}
    />
  );
});

const SidebarGroupContent = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<"div">
>(function SidebarGroupContent({ className, ...props }, ref) {
  return (
    <div
      ref={ref}
      data-slot="sidebar-group-content"
      className={cn("flex flex-col gap-1", className)}
      {...props}
    />
  );
});

const SidebarMenu = React.forwardRef<
  HTMLUListElement,
  React.ComponentProps<"ul">
>(function SidebarMenu({ className, ...props }, ref) {
  return (
    <ul
      ref={ref}
      data-slot="sidebar-menu"
      className={cn("flex flex-col gap-1", className)}
      {...props}
    />
  );
});

const SidebarMenuItem = React.forwardRef<
  HTMLLIElement,
  React.ComponentProps<"li">
>(function SidebarMenuItem({ className, ...props }, ref) {
  return (
    <li
      ref={ref}
      data-slot="sidebar-menu-item"
      className={cn("list-none", className)}
      {...props}
    />
  );
});

const SidebarMenuButton = React.forwardRef<
  HTMLButtonElement,
  React.ComponentProps<"button"> & {
    asChild?: boolean;
    isActive?: boolean;
    tooltip?: string;
  }
>(function SidebarMenuButton(
  { asChild = false, isActive = false, tooltip, className, children, ...props },
  ref
) {
  const { state } = useSidebar();
  const isCollapsed = state === "collapsed";
  const Comp = asChild ? Slot : "button";
  const button = (
    <Comp
      ref={ref as React.RefObject<HTMLButtonElement>}
      data-slot="sidebar-menu-button"
      data-active={isActive}
      className={cn(
        "flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm outline-none transition-colors",
        "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        "focus-visible:ring-1 focus-visible:ring-sidebar-ring",
        "data-[active=true]:bg-sidebar-accent data-[active=true]:text-sidebar-accent-foreground",
        "group-data-[collapsible=collapsed]:justify-center group-data-[collapsible=collapsed]:px-2",
        isActive && "bg-sidebar-accent text-sidebar-accent-foreground",
        className
      )}
      {...props}
    >
      {children}
    </Comp>
  );

  if (isCollapsed && tooltip) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{button}</TooltipTrigger>
        <TooltipContent side="right" sideOffset={8}>
          {tooltip}
        </TooltipContent>
      </Tooltip>
    );
  }
  return button;
});

const SidebarMenuSub = React.forwardRef<
  HTMLUListElement,
  React.ComponentProps<"ul">
>(function SidebarMenuSub({ className, ...props }, ref) {
  return (
    <ul
      ref={ref}
      data-slot="sidebar-menu-sub"
      className={cn(
        "mx-3 flex flex-col gap-1 border-l border-sidebar-border pl-3",
        className
      )}
      {...props}
    />
  );
});

const SidebarMenuSubItem = React.forwardRef<
  HTMLLIElement,
  React.ComponentProps<"li">
>(function SidebarMenuSubItem({ className, ...props }, ref) {
  return (
    <li
      ref={ref}
      data-slot="sidebar-menu-sub-item"
      className={cn("list-none", className)}
      {...props}
    />
  );
});

const SidebarMenuSubButton = React.forwardRef<
  HTMLButtonElement,
  React.ComponentProps<"button"> & {
    asChild?: boolean;
    isActive?: boolean;
    tooltip?: string;
  }
>(function SidebarMenuSubButton(
  { asChild = false, isActive = false, tooltip, className, children, ...props },
  ref
) {
  const { state } = useSidebar();
  const isCollapsed = state === "collapsed";
  const Comp = asChild ? Slot : "button";
  const button = (
    <Comp
      ref={ref as React.RefObject<HTMLButtonElement>}
      data-slot="sidebar-menu-sub-button"
      data-active={isActive}
      className={cn(
        "flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm outline-none transition-colors",
        "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        "focus-visible:ring-1 focus-visible:ring-sidebar-ring",
        "data-[active=true]:bg-sidebar-accent data-[active=true]:text-sidebar-accent-foreground",
        "group-data-[collapsible=collapsed]:justify-center group-data-[collapsible=collapsed]:px-2",
        isActive && "bg-sidebar-accent text-sidebar-accent-foreground",
        className
      )}
      {...props}
    >
      {children}
    </Comp>
  );

  if (isCollapsed && tooltip) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{button}</TooltipTrigger>
        <TooltipContent side="right" sideOffset={8}>
          {tooltip}
        </TooltipContent>
      </Tooltip>
    );
  }
  return button;
});

const SidebarRail = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<"div">
>(function SidebarRail({ className, ...props }, ref) {
  const { state, setWidth, toggleSidebar } = useSidebar();
  const [isDragging, setIsDragging] = React.useState(false);
  const startX = React.useRef(0);
  const startWidth = React.useRef(0);

  const handlePointerDown = (e: React.PointerEvent) => {
    if (state === "collapsed") {
      toggleSidebar();
      return;
    }
    e.preventDefault();
    startX.current = e.clientX;
    startWidth.current = parseInt(
      getComputedStyle(document.documentElement).getPropertyValue(
        "--sidebar-width"
      ) || "256",
      10
    );
    setIsDragging(true);
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
  };

  React.useEffect(() => {
    if (!isDragging) return;
    const onMove = (e: PointerEvent) => {
      const delta = e.clientX - startX.current;
      const newWidth = Math.min(
        MAX_WIDTH,
        Math.max(MIN_WIDTH, startWidth.current + delta)
      );
      setWidth(newWidth);
    };
    const onUp = () => setIsDragging(false);
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
    document.addEventListener("pointercancel", onUp);
    return () => {
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
      document.removeEventListener("pointercancel", onUp);
    };
  }, [isDragging, setWidth]);

  return (
    <div
      ref={ref}
      data-slot="sidebar-rail"
      onPointerDown={handlePointerDown}
      role="separator"
      aria-orientation="vertical"
      className={cn(
        "absolute inset-y-0 -right-4 z-20 hidden w-4 cursor-col-resize transition-colors sm:flex",
        "hover:bg-sidebar-border/80 after:absolute after:inset-y-0 after:left-1/2 after:w-[2px] after:-translate-x-1/2 after:bg-transparent hover:after:bg-sidebar-border",
        "group-data-[side=right]:-left-4 group-data-[side=right]:right-auto",
        isDragging && "bg-sidebar-border/80 after:bg-sidebar-border",
        className
      )}
      {...props}
    />
  );
});

const SidebarTrigger = React.forwardRef<
  HTMLButtonElement,
  React.ComponentProps<typeof Button>
>(function SidebarTrigger({ className, ...props }, ref) {
  const { toggleSidebar } = useSidebar();
  return (
    <Button
      ref={ref}
      variant="ghost"
      size="icon"
      onClick={toggleSidebar}
      className={cn(className)}
      {...props}
    >
      <PanelLeftClose className="h-4 w-4 group-data-[collapsible=collapsed]:hidden" />
      <PanelLeftOpen className="h-4 w-4 hidden group-data-[collapsible=collapsed]:block" />
      <span className="sr-only">Toggle sidebar</span>
    </Button>
  );
});

const SidebarInset = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<"main">
>(function SidebarInset({ className, style, ...props }, ref) {
  return (
    <main
      ref={ref}
      className={cn(
        "relative flex h-screen min-w-0 flex-col overflow-hidden",
        className
      )}
      style={style}
      {...props}
    />
  );
});

export {
  SidebarProvider,
  Sidebar,
  SidebarHeader,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarMenuSub,
  SidebarMenuSubItem,
  SidebarMenuSubButton,
  SidebarRail,
  SidebarTrigger,
  SidebarInset,
  useSidebar,
};
