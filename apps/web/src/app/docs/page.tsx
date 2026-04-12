import Link from "next/link";

const sections = [
  {
    title: "Getting started",
    body: "Connect your wallet, review Pacifica readiness, and move into Builder Studio when you are ready to assemble your first bot.",
  },
  {
    title: "Build and validate",
    body: "Use Builder Studio to define rules, validate logic, and save a draft before you deploy or publish anything to the marketplace.",
  },
  {
    title: "Operate live bots",
    body: "Open My Bots for runtime health, execution logs, and controls. Use Copy Trading when you want to monitor live follows and copied exposure.",
  },
];

export default function DocsPage() {
  return (
    <main className="min-h-screen bg-app text-neutral-50">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-10 px-6 py-20">
        <div className="max-w-3xl space-y-4">
          <span className="inline-flex rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs uppercase tracking-[0.24em] text-neutral-300">
            Docs
          </span>
          <h1 className="text-4xl font-semibold tracking-tight md:text-5xl">ClashX handbook</h1>
          <p className="text-base leading-7 text-neutral-300 md:text-lg">
            A quick map of the product so you can move from setup to live automation without guessing where each workflow lives.
          </p>
        </div>

        <div className="grid gap-5 md:grid-cols-3">
          {sections.map((section) => (
            <section key={section.title} className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
              <h2 className="text-xl font-medium">{section.title}</h2>
              <p className="mt-3 text-sm leading-6 text-neutral-300">{section.body}</p>
            </section>
          ))}
        </div>

        <div className="grid gap-5 rounded-[2rem] border border-[#dce85d]/20 bg-[#dce85d]/[0.08] p-6 md:grid-cols-[1.4fr_1fr] md:items-center">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Open the product desks</h2>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-neutral-200">
              Marketplace is where you discover strategies. Builder Studio is where you compose them. My Bots and Copy Trading are where you operate what is live.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
              <Link href="/marketplace" className="rounded-full bg-[#dce85d] px-4 py-2 text-sm font-medium text-[#090a0a]">
              Marketplace
            </Link>
            <Link href="/builder" className="rounded-full border border-white/15 px-4 py-2 text-sm font-medium text-neutral-50">
              Builder Studio
            </Link>
            <Link href="/bots" className="rounded-full border border-white/15 px-4 py-2 text-sm font-medium text-neutral-50">
              My Bots
            </Link>
          </div>
        </div>
      </div>
    </main>
  );
}
