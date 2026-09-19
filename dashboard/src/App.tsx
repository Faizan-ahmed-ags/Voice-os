import { NavLink, Navigate, Outlet, Route, Routes } from "react-router-dom"
import { Bot, CalendarClock, CalendarDays, Globe, Home as HomeIcon, LineChart, MessageSquare, Moon, Network, Cpu, NotebookPen, Sun } from "lucide-react"

import VoiceConsole from "@/components/VoiceConsole"
import Home from "@/pages/Home"
import Agent from "@/pages/Agent"
import Plan from "@/pages/Plan"
import News from "@/pages/News"
import Chats from "@/pages/Chats"
import Connections from "@/pages/Connections"
import Brain from "@/pages/Brain"
import CalendarPage from "@/pages/Calendar"
import ChartPage from "@/pages/Chart"
import JournalPage from "@/pages/Journal"
import { useTheme } from "@/lib/useTheme"
import { cn } from "@/lib/utils"

const NAV = [
  { to: "/", label: "Home", icon: HomeIcon },
  { to: "/calendar", label: "Calendar", icon: CalendarDays },
  { to: "/chart", label: "Trade Map", icon: LineChart },
  { to: "/journal", label: "Journal", icon: NotebookPen },
  { to: "/agent", label: "Agent", icon: Bot },
  { to: "/plan", label: "Plan", icon: CalendarClock },
  { to: "/news", label: "Daily News", icon: Globe },
  { to: "/chats", label: "Chats & Trades", icon: MessageSquare },
  { to: "/connections", label: "Connections", icon: Network },
  { to: "/brain", label: "Brain", icon: Cpu },
]

export default function App() {
  const { theme, toggle } = useTheme()
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-16 shrink-0 flex-col items-center gap-1 border-r border-border bg-card/40 py-4 backdrop-blur md:w-52 md:items-stretch md:px-3">
        <div className="mb-4 hidden px-2 md:block">
          <h1 className="font-mono text-xl font-bold tracking-[0.3em] text-primary">J.A.R.V.I.S.</h1>
          <p className="text-[10px] uppercase tracking-widest text-muted-foreground">halal paper trading</p>
        </div>
        <div className="mb-4 md:hidden">
          <span className="font-mono text-lg font-bold text-primary">J.</span>
        </div>
        <nav className="flex flex-1 flex-col gap-1">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-primary/15 text-primary"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground",
                )
              }
            >
              <Icon className="size-4 shrink-0" />
              <span className="hidden md:inline">{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="hidden px-3 text-[10px] leading-relaxed text-muted-foreground md:block">
          Paper trading only · educational · not financial advice
        </div>
        <button
          onClick={toggle}
          aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          title={theme === "dark" ? "Light theme" : "Dark theme"}
          className="theme-toggle mt-2 flex items-center justify-center gap-2 rounded-md border border-border px-3 py-1.5 text-xs transition-colors"
        >
          {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
          <span className="hidden md:inline">{theme === "dark" ? "Light" : "Dark"}</span>
        </button>
      </aside>

      <main className="hud-grid min-h-screen flex-1">
        <div className="mx-auto w-full max-w-6xl px-4 py-6 md:px-8 md:py-8">
          <Outlet />
        </div>
        <VoiceConsole variant="floating" />
      </main>
    </div>
  )
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<App />}>
        <Route index element={<Home />} />
        <Route path="calendar" element={<CalendarPage />} />
        <Route path="chart" element={<ChartPage />} />
        <Route path="journal" element={<JournalPage />} />
        <Route path="agent" element={<Agent />} />
        <Route path="plan" element={<Plan />} />
        <Route path="news" element={<News />} />
        <Route path="chats" element={<Chats />} />
        <Route path="connections" element={<Connections />} />
        <Route path="brain" element={<Brain />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
