import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import AiQueryBox from "../../frontend/src/components/AiQueryBox";

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe("AI query box", () => {
  it("keeps the sent question and model answer when the layer tab is reopened", async () => {
    vi.stubGlobal("fetch",vi.fn(async(url:string)=>({ok:true,json:async()=>url.includes("/ai-query") ? {caption:"id = 1",rows:[],is_sample:false} : {provider:"ollama",model:"local-model",configured:true,privacy_warning:null}})));
    const user=userEvent.setup();
    const view=render(<MemoryRouter><AiQueryBox connectionId="history" schema="public" name="roads" /></MemoryRouter>);
    await user.type(await screen.findByRole("textbox",{name:"Ask about this data"}),"Show feature 1");
    await user.click(screen.getByRole("button",{name:"Ask"}));
    expect(await screen.findByText("Show feature 1")).toBeDefined();
    expect(await screen.findByText(/0 matching rows. Filter: id = 1/)).toBeDefined();
    view.unmount();
    render(<MemoryRouter><AiQueryBox connectionId="history" schema="public" name="roads" /></MemoryRouter>);
    expect(await screen.findByText("Show feature 1")).toBeDefined();
    expect(screen.getByText(/0 matching rows. Filter: id = 1/)).toBeDefined();
  });
  it("shows set-up-AI-first when unconfigured (TRS-076)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          provider: null,
          configured: false,
          privacy_warning: null,
          ollama_default_endpoint: "http://127.0.0.1:11434/v1/chat/completions",
        }),
      })
    );
    render(
      <MemoryRouter>
        <AiQueryBox connectionId="c1" schema="" name="sample_inventory.csv" />
      </MemoryRouter>
    );
    expect(await screen.findByText(/Set up AI first/)).toBeDefined();
    expect(screen.getByRole("link", { name: "Settings" })).toBeDefined();
  });

  it("shows the privacy warning when an external API is configured (TRS-074)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          provider: "external",
          configured: true,
          privacy_warning:
            "Using an external API may send parts of your data descriptions to that provider. Use Ollama for fully private AI.",
          ollama_default_endpoint: "http://127.0.0.1:11434/v1/chat/completions",
        }),
      })
    );
    render(
      <MemoryRouter>
        <AiQueryBox connectionId="c1" schema="" name="sample_inventory.csv" />
      </MemoryRouter>
    );
    expect(await screen.findByPlaceholderText("Ask about this data…")).toBeDefined();
    expect(screen.getByText(/Using an external API may send parts of your data descriptions/)).toBeDefined();
  });

  it("shows the generated filter caption next to results (TRS-026)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string, init?: RequestInit) => {
        if (String(url).includes("/ai-query")) {
          return {
            ok: true,
            json: async () => ({
              caption: "stock_qty = 12",
              rows: [{ item_code: "A02", stock_qty: 12 }],
              is_sample: false,
            }),
          };
        }
        return {
          ok: true,
          json: async () => ({
            provider: "ollama",
            configured: true,
            privacy_warning: null,
            ollama_default_endpoint: "http://127.0.0.1:11434/v1/chat/completions",
          }),
        };
      })
    );
    render(
      <MemoryRouter>
        <AiQueryBox connectionId="c1" schema="" name="sample_inventory.csv" />
      </MemoryRouter>
    );
    await screen.findByPlaceholderText("Ask about this data…");
    await userEvent.type(screen.getByPlaceholderText("Ask about this data…"), "Which items have 12 units in stock?");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText("Showing: stock_qty = 12")).toBeDefined();
  });
});
