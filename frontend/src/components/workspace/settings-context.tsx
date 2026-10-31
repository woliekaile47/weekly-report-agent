import { createContext, useContext } from "react";

export type SettingsSection = "models" | "employee" | "limits" | "about";
export const SettingsContext = createContext<{
  openSettings: (section?: SettingsSection) => void;
}>({ openSettings: () => {} });
export const useSettingsDialog = () => useContext(SettingsContext);
