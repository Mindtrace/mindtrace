"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Building2,
  ChevronDown,
  Camera,
  Factory,
  LogOut,
  ScanSearch,
  Settings,
  Server,
  Users,
  Workflow,
} from "lucide-react";
import { useAuth } from "@/context/auth-context";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarRail,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const managementItems: {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  roles: string[];
}[] = [
  {
    href: "/organizations",
    label: "Organizations",
    icon: Building2,
    roles: ["super_admin"],
  },
  {
    href: "/plants",
    label: "Plants",
    icon: Factory,
    roles: ["super_admin"],
  },
  {
    href: "/lines",
    label: "Lines",
    icon: Workflow,
    roles: ["super_admin"],
  },
  {
    href: "/models",
    label: "Models",
    icon: Settings,
    roles: ["super_admin"],
  },
  {
    href: "/model-deployments",
    label: "Model deployments",
    icon: Server,
    roles: ["super_admin"],
  },
  {
    href: "/camera-services",
    label: "Camera services",
    icon: Camera,
    roles: ["super_admin"],
  },
  {
    href: "/cameras",
    label: "Cameras",
    icon: Camera,
    roles: ["super_admin"],
  },
  {
    href: "/camera-sets",
    label: "Camera sets",
    icon: Camera,
    roles: ["super_admin"],
  },
  {
    href: "/stage-graphs",
    label: "Stage graphs",
    icon: Workflow,
    roles: ["super_admin"],
  },
  {
    href: "/users",
    label: "Users",
    icon: Users,
    roles: ["super_admin", "admin"],
  },
];

export function AppSidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const visibleManagement = managementItems.filter(
    (item) => user && item.roles.includes(user.role)
  );
  const hasManagementAccess = visibleManagement.length > 0;

  return (
    <Sidebar side="left" className="relative">
      <SidebarHeader className="border-b border-sidebar-border">
        <div
          className="flex h-14 items-center gap-2 px-2 group-data-[collapsible=collapsed]:justify-center"
          title="Inspectra"
        >
          <ScanSearch className="h-5 w-5 shrink-0 text-sidebar-foreground" />
          <span className="truncate font-semibold group-data-[collapsible=collapsed]:hidden">
            Inspectra
          </span>
        </div>
      </SidebarHeader>
      <SidebarContent>
        {hasManagementAccess && (
          <Collapsible defaultOpen className="group/management">
            <SidebarGroup>
              <SidebarGroupLabel className="group-data-[collapsible=collapsed]:!flex group-data-[collapsible=collapsed]:items-center group-data-[collapsible=collapsed]:justify-center">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <CollapsibleTrigger className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs font-medium text-sidebar-foreground/70 outline-none transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-1 focus-visible:ring-sidebar-ring [&[data-state=open]>svg:last-of-type]:rotate-180 group-data-[collapsible=collapsed]:justify-center group-data-[collapsible=collapsed]:px-2">
                      <Settings className="h-4 w-4 shrink-0" />
                      <span className="group-data-[collapsible=collapsed]:hidden">
                        Management
                      </span>
                      <ChevronDown className="ml-auto h-4 w-4 shrink-0 transition-transform group-data-[collapsible=collapsed]:hidden" />
                    </CollapsibleTrigger>
                  </TooltipTrigger>
                  <TooltipContent side="right" sideOffset={8}>
                    Management
                  </TooltipContent>
                </Tooltip>
              </SidebarGroupLabel>
              <CollapsibleContent>
                <SidebarGroupContent>
                  <SidebarMenuSub>
                    {visibleManagement.map((item) => {
                      const Icon = item.icon;
                      const isActive =
                        pathname === item.href ||
                        pathname.startsWith(`${item.href}/`);
                      return (
                        <SidebarMenuSubItem key={item.href}>
                          <SidebarMenuSubButton
                            asChild
                            isActive={isActive}
                            tooltip={item.label}
                          >
                            <Link href={item.href}>
                              <Icon className="h-4 w-4 shrink-0" />
                              <span className="group-data-[collapsible=collapsed]:hidden">
                                {item.label}
                              </span>
                            </Link>
                          </SidebarMenuSubButton>
                        </SidebarMenuSubItem>
                      );
                    })}
                  </SidebarMenuSub>
                </SidebarGroupContent>
              </CollapsibleContent>
            </SidebarGroup>
          </Collapsible>
        )}
      </SidebarContent>
      <SidebarFooter>
        <div
          className="mb-2 truncate px-2 text-xs text-sidebar-foreground/70 group-data-[collapsible=collapsed]:hidden"
          title={user ? `${user.email} · ${user.role}` : undefined}
        >
          {user?.email} · {user?.role}
        </div>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton onClick={logout} tooltip="Sign out">
              <LogOut className="h-4 w-4 shrink-0" />
              <span className="group-data-[collapsible=collapsed]:hidden">
                Sign out
              </span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <div
        className="absolute right-0 top-1/2 z-30 flex -translate-y-1/2 translate-x-1/2"
        aria-hidden
      >
        <SidebarTrigger className="h-8 w-8 shrink-0 rounded-full border border-sidebar-border bg-sidebar shadow-sm hover:bg-sidebar-accent" />
      </div>
      <SidebarRail />
    </Sidebar>
  );
}
