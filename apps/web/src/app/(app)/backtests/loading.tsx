export default function Loading() {
  return (
    <main className="shell grid gap-6 pb-10 md:pb-12">
      <section className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[linear-gradient(135deg,#16181a,rgba(22,24,26,0.7),rgba(220,232,93,0.08))] p-6 md:p-8">
        <div className="grid gap-3">
          <div className="skeleton h-4 w-28 rounded-full" />
          <div className="skeleton h-14 w-full max-w-4xl rounded-[1.5rem]" />
          <div className="skeleton h-5 w-full max-w-3xl rounded-full" />
          <div className="skeleton h-5 w-2/3 max-w-2xl rounded-full" />
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="grid gap-6">
          <section className="grid gap-5 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5 md:p-6">
            <div className="grid gap-2">
              <div className="skeleton h-4 w-24 rounded-full" />
              <div className="skeleton h-4 w-full max-w-2xl rounded-full" />
            </div>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
              {Array.from({ length: 6 }).map((_, index) => (
                <div key={`control-skeleton-${index}`} className="grid gap-2">
                  <div className="skeleton h-3 w-20 rounded-full" />
                  <div className="skeleton h-12 w-full rounded-[1.3rem]" />
                </div>
              ))}
            </div>
          </section>

          <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
            {Array.from({ length: 6 }).map((_, index) => (
              <article
                key={`summary-skeleton-${index}`}
                className="grid gap-2 rounded-[1.6rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-4"
              >
                <div className="skeleton h-3 w-16 rounded-full" />
                <div className="skeleton h-8 w-24 rounded-md" />
              </article>
            ))}
          </section>

          <section className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
            <div className="skeleton h-[25rem] w-full rounded-[1.6rem]" />
          </section>
        </div>

        <aside className="grid gap-4 self-start xl:sticky xl:top-6">
          <section className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
            <div className="grid gap-3">
              {Array.from({ length: 5 }).map((_, index) => (
                <div
                  key={`history-skeleton-${index}`}
                  className="grid gap-3 rounded-[1.4rem] border border-[rgba(255,255,255,0.06)] bg-[#090a0a] p-4"
                >
                  <div className="skeleton h-4 w-32 rounded-full" />
                  <div className="skeleton h-3 w-24 rounded-full" />
                  <div className="skeleton h-4 w-28 rounded-full" />
                </div>
              ))}
            </div>
          </section>
        </aside>
      </section>
    </main>
  );
}
