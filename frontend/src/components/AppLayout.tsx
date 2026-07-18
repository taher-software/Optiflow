import { Outlet } from "react-router-dom";

import { Sidebar } from "./Sidebar";

/** Shell for the protected app area: fixed left sidebar + scrollable content. */
export function AppLayout() {
  return (
    <div className="flex min-h-screen bg-slate-950 text-white">
      <Sidebar />
      <main className="flex-1 overflow-x-hidden">
        <Outlet />
      </main>
    </div>
  );
}

export default AppLayout;
