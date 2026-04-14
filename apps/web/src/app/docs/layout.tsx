import { DocsSidebar } from "@/components/docs/DocsSidebar";
import { DocsHeader } from "@/components/docs/DocsHeader";
import { DocsTOC } from "@/components/docs/DocsTOC";

export default function DocsLayout({ children }: { children: React.ReactNode }) {
    return (
        <div className="min-h-screen bg-[#090a0a] text-neutral-50 selection:bg-[#dce85d]/30 selection:text-white">
            <DocsHeader />
            <div className="mx-auto flex max-w-[1440px] items-start">
                <aside className="hidden w-64 shrink-0 md:block lg:w-72">
                    <DocsSidebar />
                </aside>
                <main className="flex-1 px-6 md:px-10 lg:px-16">
                    {children}
                </main>
                <aside className="hidden w-64 shrink-0 xl:block 2xl:w-72 pr-6">
                    <DocsTOC />
                </aside>
            </div>
        </div>
    );
}
