import { Link, useMatchRoute } from "@tanstack/react-router";
import { Inbox, Scale, ScrollText, type LucideIcon } from "lucide-react";

import { Logo } from "@/components/logo";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";
import { UserMenu } from "@/components/user-menu";
import { useCases } from "@/features/disputes/use-cases";

interface NavItem {
  to: "/cases" | "/audit" | "/policy";
  label: string;
  icon: LucideIcon;
}

const NAV: NavItem[] = [
  { to: "/cases", label: "Cases", icon: Inbox },
  { to: "/audit", label: "Audit trail", icon: ScrollText },
  { to: "/policy", label: "Fairness policy", icon: Scale },
];

/** How many cases are waiting on the seller, shown beside "Cases" wherever they are in the app. */
function useNeedsYouCount() {
  return useCases().cases.filter((item) => item.status === "needs_you").length;
}

export function AppSidebar() {
  const matchRoute = useMatchRoute();
  const needsYou = useNeedsYouCount();

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <Link to="/cases">
                <Logo />
                <div className="grid flex-1 text-left leading-tight">
                  <span className="text-sm font-semibold tracking-tight">Settle</span>
                  <span className="text-xs text-muted-foreground">Dispute mediation</span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <nav aria-label="Main">
              <SidebarMenu>
                {NAV.map((item) => (
                  <SidebarMenuItem key={item.to}>
                    <SidebarMenuButton
                      asChild
                      tooltip={item.label}
                      isActive={Boolean(matchRoute({ to: item.to, fuzzy: true }))}
                    >
                      <Link
                        to={item.to}
                        // Not hidden text: browsers read that with a space before the comma.
                        aria-label={
                          item.to === "/cases" && needsYou > 0
                            ? `${item.label}, ${needsYou} waiting on you`
                            : undefined
                        }
                      >
                        <item.icon />
                        <span>{item.label}</span>
                      </Link>
                    </SidebarMenuButton>
                    {item.to === "/cases" && needsYou > 0 && (
                      <SidebarMenuBadge
                        aria-hidden
                        className="bg-warning/15 text-warning-strong peer-hover/menu-button:text-warning-strong peer-data-[active=true]/menu-button:text-warning-strong"
                      >
                        {needsYou}
                      </SidebarMenuBadge>
                    )}
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </nav>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <UserMenu />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
