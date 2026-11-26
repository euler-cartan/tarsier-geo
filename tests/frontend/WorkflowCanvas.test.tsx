import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, beforeAll, expect, it } from "vitest";
import WorkflowCanvas from "../../frontend/src/components/WorkflowCanvas";
import type { AutoGraph } from "../../frontend/src/api";

const labels = [{id:"any_change",label:"Change"},{id:"user_eq",label:"User filter"},{id:"log",label:"Log"}];
const pointerCapture = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "setPointerCapture");
beforeAll(() => Object.defineProperty(HTMLElement.prototype, "setPointerCapture", {value: () => {}, configurable: true}));
afterAll(() => {
  if (pointerCapture) Object.defineProperty(HTMLElement.prototype, "setPointerCapture", pointerCapture);
  else Reflect.deleteProperty(HTMLElement.prototype, "setPointerCapture");
});
const graph: AutoGraph = {nodes:[
  {id:"t",role:"trigger",kind:"any_change",config:{}},
  {id:"c",role:"condition",kind:"user_eq",config:{}},
  {id:"a",role:"action",kind:"log",config:{}},
],edges:[{from:"t",to:"c"}]};

function Editor({initial = graph}: {initial?: AutoGraph}) {
  const [value,setValue] = useState(initial);
  return <><WorkflowCanvas graph={value} onChange={setValue} labels={labels} trace={[]} glow={null} renderConfig={() => <p>Configuration fields</p>} /><output data-testid="graph">{JSON.stringify(value)}</output></>;
}
const savedGraph = () => JSON.parse(screen.getByTestId("graph").textContent || "{}");

it("connects a condition false port to an action and removes the connection", async () => {
  render(<Editor />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", {name:"False output of User filter"}));
  await user.click(screen.getByRole("button", {name:"Input of Log"}));
  expect(savedGraph().edges).toContainEqual({from:"c",to:"a",branch:"false"});
  await user.click(screen.getByRole("button", {name:"Remove connection to a"}));
  expect(savedGraph().edges).toEqual([{from:"t",to:"c"}]);
});

it("rejects cycles while connecting nodes", async () => {
  render(<Editor initial={{...graph,edges:[...graph.edges,{from:"c",to:"a"}]}} />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", {name:"Output of Log"}));
  await user.click(screen.getByRole("button", {name:"Input of User filter"}));
  expect(screen.getByRole("alert").textContent).toContain("cycle");
  expect(savedGraph().edges.length).toBe(2);
});

it("inserts a step into a connection without losing its source branch", async () => {
  render(<Editor initial={{...graph,edges:[{from:"c",to:"a",branch:"false"}]}} />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", {name:"Connection c to a"}));
  await user.selectOptions(screen.getByRole("combobox", {name:"Insert a step"}),"log");
  const value = savedGraph();
  const inserted = value.nodes.find((n: {id:string}) => n.id.startsWith("insert-"));
  expect(value.edges).toContainEqual({from:"c",to:inserted.id,branch:"false"});
  expect(value.edges).toContainEqual({from:inserted.id,to:"a"});
});

it("deletes a node and its incoming and outgoing connections", async () => {
  render(<Editor />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", {name:/IF User filter/}));
  await user.click(screen.getByRole("button", {name:"Delete node"}));
  expect(savedGraph().nodes.some((n: {id:string}) => n.id === "c")).toBe(false);
  expect(savedGraph().edges).toEqual([]);
});
