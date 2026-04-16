import Link from "next/link";

export default function DesktopOnlyPage() {
  return (
    <main className="min-h-screen bg-app text-neutral-50 flex items-center justify-center px-6">
      <div className="w-full max-w-xl rounded-3xl border border-white/10 bg-neutral-900/80 p-8 text-center backdrop-blur">
        <p className="text-xs uppercase tracking-[0.24em] text-neutral-400">ClashX App</p>
        <h1 className="mt-4 text-2xl font-semibold tracking-tight text-white md:text-3xl">
          For the best experience, please use your desktop.
        </h1>
        <p className="mt-4 text-sm text-neutral-300 md:text-base">
          The in-app workspace is currently optimized for larger screens.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link
            href="/"
            className="rounded-full border border-white/15 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:border-white/30 hover:bg-white/5"
          >
            Go to Home
          </Link>
          <Link
            href="/docs"
            className="rounded-full bg-[#dce85d] px-5 py-2.5 text-sm font-semibold text-[#090a0a] transition-colors hover:bg-[#e4ef6e]"
          >
            Read Docs
          </Link>
        </div>
      </div>
    </main>
  );
}
