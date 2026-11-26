import {render,screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {MemoryRouter,Route,Routes} from "react-router-dom";
import {afterEach,expect,it,vi} from "vitest";
import {ConnectionProvider} from "../../frontend/src/shell/ConnectionContext";
import {AiProvider} from "../../frontend/src/shell/AiContext";
import TopBar from "../../frontend/src/shell/TopBar";
import Sidebar from "../../frontend/src/shell/Sidebar";

afterEach(()=>{vi.unstubAllGlobals();sessionStorage.clear();});

it("keeps the selected database in Settings and preserves sidebar destinations",async()=>{
 vi.stubGlobal("fetch",vi.fn(async()=>({ok:true,json:async()=>[{id:"pg",name:"PostGIS test",type:"postgis",config:{}}]})));
 render(<MemoryRouter initialEntries={["/connections/pg/overview"]}><ConnectionProvider><AiProvider><TopBar/><Sidebar/><Routes><Route path="/connections/:connectionId/overview" element={<p>Database overview</p>}/><Route path="/settings" element={<p>Settings content</p>}/></Routes></AiProvider></ConnectionProvider></MemoryRouter>);
 await screen.findByRole("option",{name:"PostGIS test (postgis)"});
 await userEvent.click(screen.getByRole("link",{name:"Settings"}));
 expect(await screen.findByText("Settings content")).toBeDefined();
 expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("pg");
 expect(screen.getByRole("link",{name:"Statistics"}).getAttribute("href")).toBe("/connections/pg/statistics");
});
