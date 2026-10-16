"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { CopilotDrawer } from "@/components/copilot";
import { EvidenceProvider, ProvenanceLegend } from "@/components/fact";
import { RoleSwitcher } from "@/components/role";
import { Button, ErrorNote, Spinner } from "@/components/ui";
import { DataModeTag, ProjectTabs, StatusTag, TraceStepper } from "@/components/workspace";
import { useInvalidateProject, useJob, useProject } from "@/lib/api/hooks";

export default function ProjectLayout({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const project = useProject(id);
  const [copilotOpen, setCopilotOpen] = useState(false);

  return (
    <EvidenceProvider projectId={id}>
      <div className="min-h-screen">
        <header className="border-b border-rule bg-silk">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-6 py-3">
            <div className="flex min-w-0 items-center gap-4">
              <Link href="/" className="font-bold text-mask">
                QuoteLens
              </Link>
              {project.data && (
                <>
                  <h1 className="truncate text-lg font-bold">{project.data.name}</h1>
                  <StatusTag status={project.data.status} />
                  <DataModeTag mode={project.data.data_mode} />
                </>
              )}
            </div>
            <div className="flex items-center gap-4">
              <RoleSwitcher />
              <Button variant="primary" onClick={() => setCopilotOpen(true)}>
                Ask copilot
              </Button>
            </div>
          </div>
          <div className="mx-auto max-w-7xl px-6 pt-1 pb-3">
            {project.data && <TraceStepper status={project.data.status} />}
          </div>
          <div className="mx-auto max-w-7xl px-6">
            <ProjectTabs projectId={id} />
          </div>
        </header>

        <Suspense>
          <JobBanner projectId={id} />
        </Suspense>

        <main className="mx-auto max-w-7xl px-6 py-6">
          {project.isPending && <Spinner />}
          <ErrorNote error={project.error} />
          {project.data && children}
        </main>

        <footer className="mx-auto max-w-7xl border-t border-rule px-6 py-4">
          <ProvenanceLegend />
        </footer>
      </div>
      <CopilotDrawer projectId={id} open={copilotOpen} onClose={() => setCopilotOpen(false)} />
    </EvidenceProvider>
  );
}

/** Shows analysis progress when the URL carries ?job=…, then refreshes the project. */
function JobBanner({ projectId }: { projectId: string }) {
  const params = useSearchParams();
  const router = useRouter();
  const jobId = params.get("job");
  const job = useJob(jobId);
  const invalidate = useInvalidateProject(projectId);
  const status = job.data?.status;

  useEffect(() => {
    if (status === "SUCCEEDED") {
      void invalidate().then(() => router.replace(`/projects/${projectId}`));
    }
  }, [status, projectId, router, invalidate]);

  if (!jobId || !job.data || status === "SUCCEEDED") return null;
  const failed = status === "FAILED";
  return (
    <div role="status" className={failed ? "bg-blocker-tint" : "bg-mask-tint"}>
      <div className="mx-auto flex max-w-7xl items-center gap-4 px-6 py-2.5 text-sm">
        {failed ? (
          <span className="text-blocker">
            Analysis failed: {job.data.error?.message ?? "unknown error"}. Fix the mapping or file and try again.
          </span>
        ) : (
          <>
            <Spinner label={`Analyzing BOM: ${stageLabel(job.data.stage)}`} />
            <progress value={job.data.progress ?? 0} max={100} className="h-1.5 w-48 accent-mask" />
          </>
        )}
      </div>
    </div>
  );
}

function stageLabel(stage: string | null | undefined): string {
  return (
    {
      parse: "reading the file",
      save: "saving lines",
      sourcing: "pricing parts across distributors",
      impact_and_risk: "calculating cost impact and risks",
      investigating: "investigating alternates",
    }[stage ?? ""] ?? "starting"
  );
}
