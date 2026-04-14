"use client";

import { AlertTriangle, Info, Terminal, ChevronRight } from "lucide-react";
import { ReactNode } from "react";

export function DocsCallout({ children, type = "info", title }: { children: ReactNode, type?: "info" | "warning", title?: string }) {
    const isWarning = type === "warning";
    return (
        <div className={`my-6 flex items-start gap-4 rounded-2xl border p-5 ${isWarning
                ? "border-red-500/20 bg-red-500/5 text-red-100"
                : "border-[#dce85d]/20 bg-[#dce85d]/5 text-neutral-100"
            }`}>
            <div className={`mt-0.5 shrink-0 ${isWarning ? "text-red-400" : "text-[#dce85d]"}`}>
                {isWarning ? <AlertTriangle className="h-5 w-5" /> : <Info className="h-5 w-5" />}
            </div>
            <div>
                {title && <h5 className={`mb-1 font-semibold ${isWarning ? "text-red-300" : "text-[#dce85d]"}`}>{title}</h5>}
                <div className="text-sm leading-relaxed text-neutral-300">{children}</div>
            </div>
        </div>
    );
}

export function DocsStep({ number, title, children }: { number: number, title: string, children: ReactNode }) {
    return (
        <div className="relative pl-12 pb-8 last:pb-0">
            <div className="absolute left-0 top-0 flex h-8 w-8 items-center justify-center rounded-full border border-white/10 bg-black/50 text-sm font-bold text-white shadow-[0_0_15px_rgba(220,232,93,0.15)]">
                {number}
            </div>
            <div className="absolute bottom-0 left-[15px] top-10 w-px bg-white/10 last:hidden" />
            <h4 className="mt-1 mb-2 text-lg font-semibold text-white">{title}</h4>
            <div className="text-sm text-neutral-400 leading-relaxed">{children}</div>
        </div>
    );
}

export function DocsCard({ title, children, icon }: { title: string, children: ReactNode, icon?: ReactNode }) {
    return (
        <div className="group relative overflow-hidden rounded-2xl border border-white/5 bg-white/5 p-6 transition-all hover:border-[#dce85d]/30 hover:bg-white/[0.07]">
            <div className="absolute inset-0 bg-gradient-to-br from-[#dce85d]/5 to-transparent opacity-0 transition-opacity group-hover:opacity-100" />
            {icon && <div className="mb-4 inline-flex rounded-lg bg-black/50 p-2.5 text-[#dce85d] ring-1 ring-white/10">{icon}</div>}
            <h3 className="mb-2 text-base font-semibold text-white">{title}</h3>
            <div className="text-sm leading-relaxed text-neutral-400">{children}</div>
        </div>
    );
}

export function DocsCode({ code, language = "bash" }: { code: string, language?: string }) {
    return (
        <div className="my-6 overflow-hidden rounded-xl border border-white/10 bg-[#000000]">
            <div className="flex items-center justify-between border-b border-white/5 bg-white/[0.02] px-4 py-2">
                <div className="flex items-center gap-2">
                    <Terminal className="h-4 w-4 text-neutral-500" />
                    <span className="text-xs font-medium text-neutral-400">{language}</span>
                </div>
            </div>
            <div className="overflow-x-auto p-4">
                <pre className="text-sm leading-relaxed text-emerald-400 font-mono">
                    <code>{code}</code>
                </pre>
            </div>
        </div>
    );
}
