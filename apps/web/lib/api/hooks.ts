"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "./client";

const path = (pid: string) => ({ params: { path: { pid } } });

export function useProjects() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: () => unwrap(api.GET("/api/v1/projects", { params: { query: { limit: 20 } } })),
  });
}

export function useProject(pid: string) {
  return useQuery({ queryKey: ["project", pid], queryFn: () => unwrap(api.GET("/api/v1/projects/{pid}", path(pid))) });
}

export function useOverview(pid: string) {
  return useQuery({
    queryKey: ["overview", pid],
    queryFn: () => unwrap(api.GET("/api/v1/projects/{pid}/overview", path(pid))),
  });
}

export function useLines(pid: string) {
  return useQuery({
    queryKey: ["lines", pid],
    queryFn: () => unwrap(api.GET("/api/v1/projects/{pid}/lines", { params: { path: { pid }, query: { limit: 500 } } })),
  });
}

export function useLine(pid: string, lid: string | null) {
  return useQuery({
    queryKey: ["line", pid, lid],
    enabled: lid !== null,
    queryFn: () =>
      unwrap(api.GET("/api/v1/projects/{pid}/lines/{lid}", { params: { path: { pid, lid: lid ?? "" } } })),
  });
}

export function useRisks(pid: string) {
  return useQuery({ queryKey: ["risks", pid], queryFn: () => unwrap(api.GET("/api/v1/projects/{pid}/risks", path(pid))) });
}

export function useImpact(pid: string, volume: number | undefined) {
  return useQuery({
    queryKey: ["impact", pid, volume],
    enabled: volume !== undefined,
    queryFn: () => unwrap(api.GET("/api/v1/projects/{pid}/impact", { params: { path: { pid }, query: { volume } } })),
  });
}

export function useAssumptions(pid: string) {
  return useQuery({
    queryKey: ["assumptions", pid],
    queryFn: () => unwrap(api.GET("/api/v1/projects/{pid}/assumptions", path(pid))),
  });
}

export function useAlternatives(pid: string) {
  return useQuery({
    queryKey: ["alternatives", pid],
    queryFn: () => unwrap(api.GET("/api/v1/projects/{pid}/alternatives", path(pid))),
  });
}

export function useQuotes(pid: string) {
  return useQuery({ queryKey: ["quotes", pid], queryFn: () => unwrap(api.GET("/api/v1/projects/{pid}/quotes", path(pid))) });
}

export function useAudit(pid: string) {
  return useQuery({ queryKey: ["audit", pid], queryFn: () => unwrap(api.GET("/api/v1/projects/{pid}/audit", path(pid))) });
}

/** Poll a background job every 1.5 s until it finishes. */
export function useJob(jobId: string | null) {
  return useQuery({
    queryKey: ["job", jobId],
    enabled: jobId !== null,
    queryFn: () => unwrap(api.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: jobId ?? "" } } })),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "SUCCEEDED" || status === "FAILED" ? false : 1500;
    },
    staleTime: 0,
  });
}

/** After any decision, everything derived from project data may have changed. */
export function useInvalidateProject(pid: string) {
  const client = useQueryClient();
  return () =>
    Promise.all(
      ["project", "overview", "lines", "line", "risks", "impact", "alternatives", "quotes", "audit"].map((key) =>
        client.invalidateQueries({ queryKey: [key, pid] }),
      ),
    );
}

export function useProjectMutation<TArgs, TResult>(pid: string, fn: (args: TArgs) => Promise<TResult>) {
  const invalidate = useInvalidateProject(pid);
  return useMutation({ mutationFn: fn, onSuccess: () => invalidate() });
}
