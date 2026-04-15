"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { usePathname } from "next/navigation";

export function DocsHeader() {
    const pathname = usePathname();
    const segments = pathname.split('/').filter(Boolean);

    return (
        <header className="sticky top-0 z-50 flex h-16 w-full items-center justify-between border-b border-white/5 bg-[#090a0a]/80 px-6 tracking-tight backdrop-blur-xl">
            <div className="flex items-center gap-6">
                <Link href="/" className="flex items-center gap-2">
                    <div className="flex h-6 w-6 items-center justify-center rounded-md bg-[#dce85d]">
                        <span className="text-xs font-bold text-[#090a0a]">X</span>
                    </div>
                    <span className="font-semibold text-white">ClashX</span>
                </Link>
                <div className="hidden h-5 w-px bg-white/10 md:block" />
                <nav className="hidden items-center gap-4 text-sm font-medium text-neutral-400 md:flex">
                    <Link href="/docs" className="text-white">Documentation</Link>
                </nav>
            </div>

            <div className="flex items-center gap-4">
                <Link
                    href="/dashboard"
                    className="rounded-full bg-[#dce85d] px-4 py-1.5 text-sm font-medium text-[#090a0a] transition hover:bg-[#dce85d]/90"
                >
                    Dashboard <ChevronRight className="inline h-4 w-4" />
                </Link>
            </div>
        </header>
    );
}
