"use client";

import { useParams } from "next/navigation";
import { Empty, ErrorNote, PageSkeleton } from "@/components/ui";
import { useAudit } from "@/lib/api/hooks";
import { dateTime, sentence } from "@/lib/format";

export default function ActivityPage() {
  const { id } = useParams<{ id: string }>();
  const audit = useAudit(id);
  if (audit.isPending) return <PageSkeleton />;
  if (audit.error) return <ErrorNote error={audit.error} />;
  if (audit.data.items.length === 0) return <Empty title="No decisions recorded yet" />;
  return (
    <div className="relative overflow-x-auto surface rounded-[var(--radius-panel)] p-2">
      <table className="data-table">
        <thead>
          <tr>
            <th>When</th>
            <th>Who</th>
            <th>What</th>
            <th>On</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {audit.data.items.map((event) => (
            <tr key={event.id}>
              <td className="whitespace-nowrap text-ink-2">{dateTime(event.at)}</td>
              <td className="whitespace-nowrap">{sentence(event.actor_role)}</td>
              <td className="whitespace-nowrap font-semibold">{sentence(event.action)}</td>
              <td className="code text-xs break-all">{event.target}</td>
              <td className="max-w-md text-ink-2">{event.reason ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
