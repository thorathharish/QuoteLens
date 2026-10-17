import Link from "next/link";
import { Brand } from "@/components/workspace";

export default function NotFound() {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b border-rule bg-[var(--header-bg)] backdrop-blur-xl">
        <div className="mx-auto w-full max-w-7xl px-4 py-3 sm:px-6">
          <Brand />
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 pt-16 pb-24 sm:px-6">
        <h1 className="text-display max-w-[14ch]">This page does not exist.</h1>
        <p className="mt-6 max-w-[34rem] text-lg text-ink-2">
          The link may be from an earlier session: projects are kept in memory while running locally, so they are
          cleared when the api restarts.
        </p>
        <p className="mt-9 flex flex-wrap items-center gap-x-5 gap-y-3">
          <Link
            href="/"
            className="metal inline-flex min-h-11 items-center rounded-lg px-5 text-xs font-semibold tracking-[0.12em] uppercase transition-[filter] hover:brightness-110 active:translate-y-px"
          >
            Go to the start page
          </Link>
        </p>
      </main>
    </div>
  );
}
