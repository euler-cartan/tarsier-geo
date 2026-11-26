import { createContext, ReactNode, useCallback, useContext, useMemo, useState } from "react";

export type AiJob = "query" | "explain-changes" | "explain-quality" | "build-automation";

export interface AiOpen {
  job?: AiJob;
  schema?: string;
  name?: string;
  checkId?: string;
  seed?: string;
}

interface AiState {
  open: boolean;
  job: AiJob;
  schema: string;
  name: string;
  checkId: string;
  seed: string;
  draftTick: number;
  show: (opts?: AiOpen) => void;
  hide: () => void;
  notifyDraft: () => void;
}

const AiContext = createContext<AiState>({
  open: false,
  job: "explain-changes",
  schema: "",
  name: "",
  checkId: "",
  seed: "",
  draftTick: 0,
  show: () => undefined,
  hide: () => undefined,
  notifyDraft: () => undefined,
});

export function AiProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [job, setJob] = useState<AiJob>("explain-changes");
  const [schema, setSchema] = useState("");
  const [name, setName] = useState("");
  const [checkId, setCheckId] = useState("");
  const [seed, setSeed] = useState("");
  const [draftTick, setDraftTick] = useState(0);

  const show = useCallback((opts?: AiOpen) => {
    setJob(opts?.job ?? "explain-changes");
    setSchema(opts?.schema ?? "");
    setName(opts?.name ?? "");
    setCheckId(opts?.checkId ?? "");
    setSeed(opts?.seed ?? "");
    setOpen(true);
  }, []);

  const hide = useCallback(() => setOpen(false), []);
  const notifyDraft = useCallback(() => setDraftTick((n) => n + 1), []);
  const value = useMemo(
    () => ({ open, job, schema, name, checkId, seed, draftTick, show, hide, notifyDraft }),
    [open, job, schema, name, checkId, seed, draftTick, show, hide, notifyDraft]
  );
  return <AiContext.Provider value={value}>{children}</AiContext.Provider>;
}

export function useAi(): AiState {
  return useContext(AiContext);
}
