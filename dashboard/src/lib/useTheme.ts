import { useCallback, useEffect, useState } from "react"

export type Theme = "dark" | "light"

const KEY = "jarvis-theme"

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      return (localStorage.getItem(KEY) as Theme) || "dark"
    } catch {
      return "dark"
    }
  })

  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle("light", theme === "light")
    root.classList.toggle("theme-scope", true)
    root.style.colorScheme = theme
    try {
      localStorage.setItem(KEY, theme)
    } catch {
      /* private mode */
    }
  }, [theme])

  const toggle = useCallback(() => {
    setTheme((t) => (t === "dark" ? "light" : "dark"))
  }, [])

  return { theme, toggle }
}
