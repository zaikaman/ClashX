"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { docsConfig } from "@/lib/docs-config";

export function DocsSidebar() {
    const pathname = usePathname();

    return (
        <div className="sticky top-16 h-[calc(100vh-4rem)] overflow-y-auto border-r border-white/5 bg-[#090a0a] py-8 pr-6 pl-6 custom-scrollbar">
            <div className="flex flex-col gap-8">
                {docsConfig.sidebarNav.map((group, index) => (
                    <div key={index}>
                        <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-neutral-500">
                            {group.title}
                        </h4>
                        <ul className="space-y-1 my-0 list-none pl-0">
                            {group.items?.map((item, itemIndex) => {
                                const isActive = pathname === item.href || pathname?.startsWith(item.href + "/");
                                return (
                                    <li key={itemIndex}>
                                        <Link
                                            href={item.href || "#"}
                                            className={`block rounded-md px-3 py-2 text-sm transition-colors ${isActive
                                                    ? "bg-[#dce85d]/10 text-[#dce85d] font-medium"
                                                    : "text-neutral-400 hover:bg-white/5 hover:text-white"
                                                }`}
                                        >
                                            {item.title}
                                        </Link>
                                    </li>
                                );
                            })}
                        </ul>
                    </div>
                ))}
            </div>
        </div>
    );
}
