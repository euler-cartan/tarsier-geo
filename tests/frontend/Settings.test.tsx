import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Settings from "../../frontend/src/screens/Settings";

const UNCONFIGURED = {
  provider: null,
  endpoint_url: null,
  model: null,
  api_key_set: false,
  configured: false,
  privacy_warning: null,
  ollama_default_endpoint: "http://127.0.0.1:11434/v1/chat/completions",
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Settings AI section", () => {
  it("does not contact OpenRouter when saved settings first load", async () => {
    const fetcher = vi.fn(async (url: string) => ({ok: true, json: async () => {
      if (url === "/api/settings/ai") return {...UNCONFIGURED, provider: "external", endpoint_url: "https://openrouter.ai/api/v1/chat/completions", model: "saved-model", configured: true};
      if (url.includes("/ai/models")) return {models: []};
      if (url === "/api/connections") return [];
      if (url.includes("/api/about")) return {version: "1.0.0-rc2", license: "Apache-2.0", links: []};
      return {};
    }}));
    vi.stubGlobal("fetch", fetcher);
    render(<MemoryRouter><Settings /></MemoryRouter>);
    expect(await screen.findByText("Select Refresh models to load OpenRouter models.")).toBeDefined();
    expect(await screen.findByText("Version 1.0.0-rc2")).toBeDefined();
    await new Promise(resolve => setTimeout(resolve, 400));
    expect(fetcher.mock.calls.some(([url]) => url.includes("/ai/models"))).toBe(false);
    await userEvent.click(screen.getByRole("button", {name: "Refresh models"}));
    await waitFor(() => expect(fetcher.mock.calls.some(([url]) => url.includes("provider=external"))).toBe(true));
  });

  it("discovers downloaded models and switches to the OpenRouter catalogue", async () => {
    const fetcher = vi.fn(async (url: string) => ({ok: true,json: async () => {
      if (url.includes("/ai/models")) return {models: url.includes("provider=external") ? [{id:"vendor/chat",name:"Vendor Chat"}] : [{id:"local:8b",name:"local:8b"}]};
      if (url === "/api/connections") return [];
      if (url.includes("/appearance")) return {theme:"light"};
      if (url.includes("/api/about")) return {version:"0.1.0",license:"Apache-2.0",links:[]};
      return UNCONFIGURED;
    }}));
    vi.stubGlobal("fetch",fetcher);
    render(<MemoryRouter><Settings /></MemoryRouter>);
    const user = userEvent.setup();
    const input = await screen.findByRole("combobox",{name:"Model name"});
    await user.click(input);
    await user.click(await screen.findByRole("option",{name:"local:8b"}));
    expect((input as HTMLInputElement).value).toBe("local:8b");
    expect(screen.queryByLabelText(/API key/)).toBeNull();
    await user.click(screen.getByRole("radio",{name:/OpenRouter API/}));
    await user.click(input);
    await user.click(await screen.findByRole("option",{name:/vendor\/chat/}));
    expect((input as HTMLInputElement).value).toBe("vendor/chat");
    expect(screen.getByLabelText(/OpenRouter API key/)).toBeDefined();
    expect(fetcher.mock.calls.some(([url]) => url.includes("provider=external"))).toBe(true);
  });

  it("shows the privacy warning when External API is selected (TRS-074)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        Promise.resolve({
          ok: true,
          json: async () =>
            url === "/api/connections" ? [] : url.includes("/appearance") ? {theme: "light"} : url.includes("/api/about")
              ? { version: "0.1.0", license: "Apache-2.0", links: [] }
              : url.includes("/notifications")
                ? { host: null, port: null, security: null, sender: null, username_set: false, password_set: false }
                : UNCONFIGURED,
        })
      )
    );
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>
    );

    await screen.findByText("AI configuration");
    expect(screen.queryByLabelText(/API key/)).toBeNull();
    await userEvent.click(screen.getByRole("radio", { name: /OpenRouter API/ }));
    expect(screen.getByLabelText(/OpenRouter API key/)).toBeDefined();
    expect(
      screen.getByText(/Using an external API may send parts of your data descriptions/)
    ).toBeDefined();
  });
});
