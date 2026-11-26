import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AiProvider, useAi } from "../../frontend/src/shell/AiContext";
import AiPanel from "../../frontend/src/shell/AiPanel";

afterEach(() => {
  vi.unstubAllGlobals();
});

function Opener() {
  const ai = useAi();
  return (
    <button type="button" onClick={() => ai.show({ job: "explain-changes" })}>
      Open AI
    </button>
  );
}

describe("AI panel", () => {
  it("prompts to set up AI when unconfigured", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          configured: false,
          privacy_warning: null,
          provider: null,
          endpoint_url: null,
          model: null,
          api_key_set: false,
          ollama_default_endpoint: "http://127.0.0.1:11434/v1/chat/completions",
        }),
      }))
    );
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <AiProvider>
          <Opener />
          <AiPanel />
        </AiProvider>
      </MemoryRouter>
    );
    await user.click(screen.getByRole("button", { name: "Open AI" }));
    expect(await screen.findByText(/Set up AI in Settings/)).toBeDefined();
    expect(screen.getByRole("link", { name: "Open Settings" })).toBeDefined();
  });

  it("shows a thinking state while the model responds", async () => {
    let finish: (value: unknown) => void = () => undefined;
    const hang = new Promise((resolve) => {
      finish = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/settings/ai") && !String(url).includes("/chat")) {
          return {
            ok: true,
            json: async () => ({
              configured: true,
              privacy_warning: null,
              provider: "ollama",
              endpoint_url: "http://127.0.0.1:11434/v1/chat/completions",
              model: "test",
              api_key_set: false,
              ollama_default_endpoint: "http://127.0.0.1:11434/v1/chat/completions",
            }),
          };
        }
        await hang;
        return { ok: true, json: async () => ({ job: "explain-changes", text: "No changes today." }) };
      })
    );
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/connections/c1/overview"]}>
        <Routes>
          <Route
            path="/connections/:connectionId/*"
            element={
              <AiProvider>
                <Opener />
                <AiPanel />
              </AiProvider>
            }
          />
        </Routes>
      </MemoryRouter>
    );
    await user.click(screen.getByRole("button", { name: "Open AI" }));
    const box = await screen.findByRole("textbox", { name: "Message to AI assistant" });
    expect(screen.getByRole("link", { name: /test · Ollama · Local/ })).toBeDefined();
    await user.type(box, "What changed?");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByRole("status", { name: "Thinking" })).toBeDefined();
    finish(undefined);
  });
});
