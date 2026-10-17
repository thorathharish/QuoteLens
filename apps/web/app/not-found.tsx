import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="mx-auto w-full max-w-6xl px-6 py-5">
        <Link href="/" className="rounded-md text-xl font-bold tracking-tight text-mask">
          QuoteLens
        </Link>
      </header>
      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-6 pt-16 pb-24">
        <h1 className="text-display max-w-[14ch] font-bold">This page does not exist.</h1>
        <p className="mt-6 max-w-[34rem] text-lg text-ink-2">
          The link may be from an earlier session: projects are kept in memory while running locally, so they are
          cleared when the api restarts.
        </p>
        <p className="mt-9 flex flex-wrap items-center gap-x-5 gap-y-3">
          <Link
            href="/"
            className="rounded-md bg-mask px-5 py-3 font-semibold text-silk transition-colors hover:bg-mask-2 active:translate-y-px"
          >
            Go to the start page
          </Link>
        </p>
      </main>
    </div>
  );
}
