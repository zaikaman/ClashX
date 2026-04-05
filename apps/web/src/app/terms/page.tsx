export default function TermsPage() {
  return (
    <main className="min-h-screen bg-app text-neutral-50">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-8 px-6 py-20">
        <div className="space-y-4">
          <span className="inline-flex rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs uppercase tracking-[0.24em] text-neutral-300">
            Terms
          </span>
          <h1 className="text-4xl font-semibold tracking-tight md:text-5xl">ClashX terms overview</h1>
          <p className="text-base leading-7 text-neutral-300 md:text-lg">
            This page is a product-facing placeholder for platform terms and launch policies. Replace it with your final legal copy before production launch.
          </p>
        </div>

        <section className="rounded-[2rem] border border-white/10 bg-white/[0.04] p-6 md:p-8">
          <div className="space-y-6 text-sm leading-7 text-neutral-300">
            <p>
              ClashX provides tooling for strategy creation, monitoring, and copy-trading workflows. Users remain responsible for the strategies they run,
              the wallets they connect, and the risk controls they choose.
            </p>
            <p>
              Market data, strategy metrics, and creator rankings can change quickly. Nothing shown in the product should be treated as a guarantee of future performance.
            </p>
            <p>
              Before launch, replace this placeholder with your final terms of service, risk disclosures, and any jurisdiction-specific restrictions required for your release.
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}
