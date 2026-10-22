"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ArrowUpRight,
  Bell,
  Bookmark,
  CalendarDays,
  ChevronDown,
  ChevronsUpDown,
  CheckCheck,
  CircleHelp,
  ClipboardList,
  GraduationCap,
  LayoutDashboard,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  UserRound,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { profileCompletion } from "./data";
import { useScholar } from "./store";

const navigation = [
  { label: "Dashboard", to: "/", icon: LayoutDashboard },
  { label: "Find Scholarships", to: "/scholarships", icon: Search },
  { label: "My Applications", to: "/applications", icon: ClipboardList },
  { label: "Saved Scholarships", to: "/saved", icon: Bookmark },
  { label: "My Profile", to: "/profile", icon: UserRound },
];

function isActive(pathname, to) {
  return to === "/" ? pathname === "/" : pathname === to || pathname.startsWith(`${to}/`);
}

function initialsOf(name) {
  return String(name || "")
    .split(" ")
    .filter(Boolean)
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

function Avatar({ name, small = false }) {
  const initials = initialsOf(name);
  return <span className={`avatar ${small ? "avatar-small" : ""}`}>{initials || <UserRound size={small ? 14 : 16} />}</span>;
}

export function AppShell({ children }) {
  const pathname = usePathname() || "/";
  const [collapsed, setCollapsed] = useState(false);
  const [mobile, setMobile] = useState(false);
  const [notifications, setNotifications] = useState(false);
  const [read, setRead] = useState(false);
  const [help, setHelp] = useState(false);
  const [account, setAccount] = useState(false);
  const { profile, saved, notice, notify } = useScholar();
  const current = navigation.find((n) => isActive(pathname, n.to))?.label || "Eligibility Checker";
  const displayName = profile.name || "Student";
  const completion = profileCompletion(profile);

  return (
    <div className={`app-shell ${collapsed ? "sidebar-collapsed" : ""}`}>
      <aside className={`app-sidebar ${mobile ? "mobile-open" : ""}`} aria-label="Main navigation">
        <Link href="/" className="brand" onClick={() => setMobile(false)}>
          <span className="brand-icon">
            <GraduationCap size={24} />
          </span>
          <span className="sidebar-label">
            ScholarPath <span className="brand-ai">AI</span>
          </span>
        </Link>
        <div className="sidebar-section-label sidebar-label">STUDENT WORKSPACE</div>
        <nav>
          {navigation.map((n) => (
            <Link
              key={n.to}
              href={n.to}
              className={isActive(pathname, n.to) ? "nav-item active" : "nav-item"}
              aria-current={isActive(pathname, n.to) ? "page" : undefined}
              title={n.label}
              onClick={() => setMobile(false)}
            >
              <n.icon size={19} />
              <span className="sidebar-label">{n.label}</span>
              {n.to === "/saved" && <span className="nav-count sidebar-label">{saved.length}</span>}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-help sidebar-label">
            <div className="flex items-center gap-2">
              <span className="support-icon">
                <CircleHelp size={18} />
              </span>
              <strong>A little help goes a long way</strong>
            </div>
            <p>We’re here for your next step.</p>
            <Button variant="outline" className="w-full" onClick={() => setHelp(true)}>
              Help & Support <ArrowUpRight />
            </Button>
          </div>
          <Button variant="ghost" className="sidebar-profile" onClick={() => setAccount(true)} aria-label="Open account menu">
            <Avatar name={profile.name} />
            <span className="sidebar-label profile-text">
              <strong>{displayName}</strong>
              <span>Student account</span>
            </span>
            <ChevronsUpDown size={15} className="sidebar-label" />
          </Button>
        </div>
      </aside>
      {mobile && <div className="mobile-scrim" onClick={() => setMobile(false)} />}
      <div className="app-main">
        <header className="top-header">
          <div className="flex min-w-0 items-center gap-3">
            <Button
              size="icon"
              variant="ghost"
              className="desktop-toggle text-muted-foreground"
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              onClick={() => setCollapsed(!collapsed)}
            >
              {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
            </Button>
            <Button size="icon" variant="ghost" className="mobile-toggle" aria-label="Open navigation" onClick={() => setMobile(!mobile)}>
              <Menu />
            </Button>
            <span className="header-workspace">
              Workspace <span>/</span>
            </span>
            <span className="truncate header-title">{current}</span>
          </div>
          <div className="flex shrink-0 items-center gap-2 sm:gap-5">
            <Button variant="ghost" size="sm" asChild className="header-search">
              <Link href="/scholarships">
                <Search />
                Search scholarships
              </Link>
            </Button>
            <span className="header-divider" />
            <div className="relative">
              <Button size="icon" variant="ghost" aria-label="Notifications" title="Notifications" onClick={() => setNotifications(true)}>
                <Bell />
                {!read && <span className="notification-dot" />}
              </Button>
            </div>
            <Button variant="ghost" className="account-trigger" aria-label="Open account menu" onClick={() => setAccount(true)}>
              <Avatar name={profile.name} small />
              <ChevronDown size={14} />
            </Button>
          </div>
        </header>
        <main className="page-content">{children}</main>
        <footer className="app-footer">
          <span>© 2026 ScholarPath AI</span>
          <span>Your next opportunity starts here.</span>
        </footer>
      </div>
      {notice && (
        <div className="toast-message" role="status">
          <CheckCheck size={18} />
          {notice}
          <Button variant="ghost" size="icon" aria-label="Dismiss notification" onClick={() => notify("")}>
            <X />
          </Button>
        </div>
      )}

      <Dialog open={notifications} onOpenChange={setNotifications}>
        <DialogContent>
          <DialogTitle>Notifications</DialogTitle>
          <DialogDescription>Updates from your own workspace on this device.</DialogDescription>
          <div className="notification-list">
            <div>
              <CalendarDays />
              <section>
                <strong>Deadline alerts are not available yet</strong>
                <p>The current scholarship data has no application dates, so ScholarPath cannot warn you about deadlines. Check each official website.</p>
              </section>
            </div>
            <div>
              <Bookmark />
              <section>
                <strong>Your saved opportunities</strong>
                <p>
                  You have {saved.length} scholarship{saved.length === 1 ? "" : "s"} saved for later.
                </p>
                <Link href="/saved" onClick={() => setNotifications(false)}>
                  View saved scholarships
                </Link>
              </section>
            </div>
            <div>
              <UserRound />
              <section>
                <strong>{completion === 100 ? "Your profile is complete" : "Complete your profile"}</strong>
                <p>
                  {completion === 100
                    ? "Review your details whenever they change so eligibility checks stay accurate."
                    : `Your profile is ${completion}% complete. More details mean fewer “can't tell yet” results.`}
                </p>
                <Link href="/profile" onClick={() => setNotifications(false)}>
                  {completion === 100 ? "Review profile" : "Complete profile"}
                </Link>
              </section>
            </div>
          </div>
          <Button
            variant="outline"
            onClick={() => {
              setRead(true);
              setNotifications(false);
            }}
          >
            Mark all as read
          </Button>
        </DialogContent>
      </Dialog>

      <Dialog open={help} onOpenChange={setHelp}>
        <DialogContent>
          <DialogTitle>Help & Support</DialogTitle>
          <DialogDescription>ScholarPath AI student support</DialogDescription>
          <div className="help-content">
            <h3>Are these scholarships verified?</h3>
            <p>
              Not yet. Records come from the ScholarPath data pipeline and are labelled “Unverified” until a reviewer confirms them against an official
              source. Always confirm the scheme, dates and requirements with the provider before applying.
            </p>
            <h3>Where are my details saved?</h3>
            <p>
              Your profile, saved scholarships and application statuses stay in this browser. Your details are sent to the ScholarPath API only when
              you check eligibility, and are not stored there.
            </p>
            <h3>How is eligibility checked?</h3>
            <p>
              The ScholarPath API compares your details with each scholarship’s listed criteria using fixed rules, with no scores or AI guesses. It only
              answers “Eligible” or “Not Eligible” when the rules are verified and backed by evidence; otherwise it says “Can’t Tell Yet” and explains
              every criterion.
            </p>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={account} onOpenChange={setAccount}>
        <DialogContent>
          <DialogTitle>{displayName}</DialogTitle>
          <DialogDescription>Student profile · stored on this device</DialogDescription>
          <Button variant="outline" asChild>
            <Link href="/profile" onClick={() => setAccount(false)}>
              <UserRound />
              Edit profile & preferences
            </Link>
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              setAccount(false);
              setHelp(true);
            }}
          >
            <CircleHelp />
            Help & Support
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}
