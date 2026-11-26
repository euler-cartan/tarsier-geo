import { Ico } from "./components/Icon";
import Snapshots from "./screens/Snapshots";
import { lazy, Suspense } from "react";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { EmptyState } from "./components/States";
import AddConnection from "./AddConnection";
import Layout from "./shell/Layout";
import ConnectionList from "./screens/ConnectionList";
import Overview from "./screens/Overview";
import ItemDetail from "./screens/ItemDetail";
import Changes from "./screens/Changes";
import Alerts from "./screens/Alerts";
import Automations from "./screens/Automations";
import Settings from "./screens/Settings";
import GlobalStatistics from "./screens/GlobalStatistics";

const RelationshipGraph = lazy(() => import("./screens/RelationshipGraph"));
const Flowchart = lazy(() => import("./screens/Flowchart"));

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<ConnectionList />} />
          <Route path="/connections/new" element={<AddConnection />} />
          <Route path="/connections/:connectionId/overview" element={<Overview />} />
          <Route path="/connections/:connectionId/statistics" element={<GlobalStatistics />} />
          <Route path="/connections/:connectionId/changes" element={<Changes />} />
          <Route path="/connections/:connectionId/alerts" element={<Alerts />} />
          <Route path="/connections/:connectionId/automations" element={<Automations />} />
          <Route path="/connections/:connectionId/flowchart" element={<Suspense fallback={<p className="t-body-md">Loading flowchart.</p>}><Flowchart /></Suspense>} />
          <Route path="/connections/:connectionId/graph" element={<Suspense fallback={<p className="t-body-md">Loading graph.</p>}><RelationshipGraph /></Suspense>} />
          <Route path="/connections/:connectionId/items" element={<ItemDetail />} />
          <Route path="/connections/:connectionId/snapshots" element={<Snapshots />} />
          <Route path="/settings" element={<Settings />} />
          {/* An address that matches no screen used to render a blank page. */}
          <Route
            path="*"
            element={
              <EmptyState title="Page not found" action={<Link className="button-primary-dark" to="/"><Ico t="Back to your connections" /></Link>}>
                This address does not match any Tarsier screen.
              </EmptyState>
            }
          />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
