import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import QualityPanel from "../../frontend/src/screens/QualityPanel";
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("uses a column picker for comparison and no value for uniqueness", async () => {
  const fetch=vi.fn(async (_url: string, init?: RequestInit) => ({ok:true,json:async () => init?.method==="POST" ? {id:"r"} : {
    checks:{},rules:[],vector_layers:[],boundary_schema:null,boundary_name:null,
    columns:[{name:"land_value",type:"numeric"},{name:"total_value",type:"numeric"}]
  }}));
  vi.stubGlobal("fetch",fetch);
  const item={schema:"qa",name:"fixture",kind:"tabular"} as Parameters<typeof QualityPanel>[0]["item"];
  render(<QualityPanel connectionId="c" item={item} />);
  await screen.findByText("Custom rules");
  const user=userEvent.setup();
  await user.type(screen.getByLabelText("Field"),"total_value");
  await user.selectOptions(screen.getByLabelText("Operator"),"column_gte");
  await user.selectOptions(screen.getByLabelText("Compare column"),"land_value");
  await user.click(screen.getByRole("button",{name:"Add rule"}));
  const posted=fetch.mock.calls.filter(call=>call[1]?.method==="POST");
  expect(JSON.parse(posted[0][1]!.body as string)).toMatchObject({operator:"column_gte",value:"land_value"});
  await user.selectOptions(screen.getByLabelText("Operator"),"is_unique");
  expect(screen.queryByLabelText("Value")).toBeNull();
  expect(screen.queryByLabelText("Compare column")).toBeNull();
  await user.type(screen.getByLabelText("Field"),"total_value");
  await user.click(screen.getByRole("button",{name:"Add rule"}));
  const unique=fetch.mock.calls.filter(call=>call[1]?.method==="POST").at(-1);
  expect(JSON.parse(unique![1]!.body as string)).toMatchObject({operator:"is_unique",value:null});
});
