import { createContext, useContext } from "react";
export const AccessContext = createContext({admin: true, public: false});
export const useAccess = () => useContext(AccessContext);
