import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { useMatch } from "react-router-dom";

const ConnectionContext = createContext<string | null | undefined>(undefined);
const key = "tarsier-active-connection";

export function ConnectionProvider({children}: {children: ReactNode}) {
  const routeId = useMatch("/connections/:connectionId/:section/*")?.params.connectionId;
  const [lastId, setLastId] = useState(() => sessionStorage.getItem(key));
  useEffect(() => {
    if (routeId) {setLastId(routeId); sessionStorage.setItem(key, routeId);}
  }, [routeId]);
  return <ConnectionContext.Provider value={routeId || lastId}>{children}</ConnectionContext.Provider>;
}

export function useSelectedConnection() {
  const context = useContext(ConnectionContext);
  const routeId = useMatch("/connections/:connectionId/:section/*")?.params.connectionId;
  return context === undefined ? routeId : context;
}
