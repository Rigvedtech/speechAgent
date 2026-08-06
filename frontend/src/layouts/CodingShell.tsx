import { Outlet } from 'react-router-dom'

/** Full-bleed shell for candidate coding links — no recruiter navbar. */
export function CodingShell() {
  return (
    <div className="h-dvh w-screen overflow-hidden bg-[#0f1115] text-zinc-200 antialiased">
      <Outlet />
    </div>
  )
}
