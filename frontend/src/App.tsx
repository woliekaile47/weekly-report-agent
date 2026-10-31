// Workspace shell adapted from DeerFlow e0f5483 (MIT).
import { useEffect, useMemo, useState } from "react";
import { Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { WorkspaceSidebar } from "@/components/workspace/workspace-sidebar";
import { WorkspaceHeader } from "@/components/workspace/workspace-header";
import { SettingsDialog } from "@/components/workspace/settings-dialog";
import {
  SettingsContext,
  type SettingsSection,
} from "@/components/workspace/settings-context";
import { HistoryPage } from "@/pages/HistoryPage";
import { RunDetailPage } from "@/pages/RunDetailPage";
import { UploadPage } from "@/pages/UploadPage";

export default function App() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [section, setSection] = useState<SettingsSection>("models");
  const settings = useMemo(
    () => ({
      openSettings: (next: SettingsSection = "models") => {
        setSection(next);
        setSettingsOpen(true);
      },
    }),
    [],
  );
  useEffect(() => {
    if (pathname.startsWith("/settings")) {
      const part = pathname.split("/")[2];
      setSection(
        part === "employee" || part === "limits" || part === "about"
          ? part
          : "models",
      );
      setSettingsOpen(true);
    }
  }, [pathname]);
  return (
    <SettingsContext.Provider value={settings}>
      <SidebarProvider
        defaultOpen={
          !document.cookie.split("; ").includes("sidebar_state=false")
        }
        className="h-svh min-h-0 overflow-hidden"
      >
        <WorkspaceSidebar />
        <SidebarInset className="h-svh min-h-0 min-w-0 overflow-hidden">
          <Routes>
            <Route path="/" element={<UploadPage />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="/runs/:id" element={<RunDetailPage />} />
            <Route
              path="/settings/*"
              element={
                <>
                  <WorkspaceHeader title="工作空间设置" />
                  <div className="grid flex-1 place-items-center">
                    <button
                      className="secondary"
                      onClick={() => setSettingsOpen(true)}
                    >
                      打开设置
                    </button>
                  </div>
                </>
              }
            />
            <Route
              path="*"
              element={
                <>
                  <WorkspaceHeader title="页面不存在" />
                  <div className="grid flex-1 place-items-center">
                    <a className="secondary" href="/history">
                      返回任务历史
                    </a>
                  </div>
                </>
              }
            />
          </Routes>
        </SidebarInset>
        <SettingsDialog
          open={settingsOpen}
          section={section}
          onSectionChange={setSection}
          onOpenChange={(open) => {
            setSettingsOpen(open);
            if (!open && pathname.startsWith("/settings"))
              navigate("/", { replace: true });
          }}
        />
      </SidebarProvider>
    </SettingsContext.Provider>
  );
}
