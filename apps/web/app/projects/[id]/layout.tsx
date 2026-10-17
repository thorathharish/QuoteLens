"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { CopilotDrawer } from "@/components/copilot";
import { EvidenceProvider, ProvenanceLegend } from "@/components/fact";
import { RoleSwitcher } from "@/components/role";
import { Button, ErrorNote, PageSkeleton, Spinner } from "@/components/ui";
import { DataModeTag, ProjectTabs, StatusTag, TraceStepper } from "@/components/workspace";
import { useInvalidateProject, useJob, useProject } from "@/lib/api/hooks";

export default function ProjectLayout({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const project = useProject(id);
  const [copilotOpen, setCopilotOpen] = useState(false);

  return (
    <EvidenceProvider projectId={id}>
      <div className="flex min-h-dvh flex-col">
        <header className="bg-silk">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-6 gap-y-3 px-6 py-3.5">
            <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1">
              <Link href="/" className="rounded-md text-lg font-bold tracking-tight text-mask">
                QuoteLens
              </Link>
              {project.data && (
                <>
                  <h1 className="truncate text-lg font-semibold">{project.data.name}</h1>
                  <span className="flex items-center gap-2">
                    <StatusTag status={project.data.status} />
                    <DataModeTag mode={project.data.data_mode} />
                  </span>
                </>
              )}
            </div>
            <div className="flex items-center gap-4">
              <RoleSwitcher />
              <Button variant="primary" onClick={() => setCopilotOpen(true)} aria-expanded={copilotOpen}>
                Ask copilot
              </Button>
            </div>
          </div>
        </header>
        <div className="bg-laminate-2">
          <div className="mx-auto flex max-w-7xl flex-col gap-3 px-6 pt-4">
            {project.data && <TraceStepper status={project.data.status} />}
            <ProjectTabs projectId={id} />
          </div>
        </div>

        <Suspense>
          <JobBanner projectId={id} />
        </Suspense>

        <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-6 py-8">
          {project.isPending && <PageSkeleton />}
          <ErrorNote error={project.error} />
          {project.data && children}
        </main>

        <footer className="bg-laminate-2">
          <div className="mx-auto max-w-7xl px-6 py-4">
            <ProvenanceLegend />
          </div>
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
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-4 px-6 py-3 text-sm">
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
