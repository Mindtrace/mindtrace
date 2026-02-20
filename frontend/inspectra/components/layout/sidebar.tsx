"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Building2, LogOut, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";
import { cn } from "@/lib/utils";

const navItems: {
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
    href: "/users",
    label: "Users",
    icon: Users,
    roles: ["super_admin", "admin"],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  const visible = navItems.filter(
    (item) => user && item.roles.includes(user.role)
  );

  return (
    <aside className="flex w-56 flex-col border-r bg-card">
      <div className="flex h-14 items-center gap-2 border-b px-4">
        <span className="font-semibold">Inspectra</span>
      </div>
      <nav className="flex flex-1 flex-col gap-1 p-2">
        {visible.map((item) => {
          const Icon = item.icon;
          const isActive =
            pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link key={item.href} href={item.href} className="cursor-pointer">
              <Button
                variant={isActive ? "secondary" : "ghost"}
                className={cn(
                  "w-full justify-start gap-2",
                  !isActive && "text-muted-foreground"
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Button>
            </Link>
          );
        })}
      </nav>
      <div className="border-t p-2">
        <div
          className="mb-2 truncate px-2 text-xs text-muted-foreground"
          title={user ? `${user.email} · ${user.role}` : undefined}
        >
          {user?.email} · {user?.role}
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start gap-2"
          onClick={logout}
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </Button>
      </div>
    </aside>
  );
}
