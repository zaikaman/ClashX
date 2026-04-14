"use client";

import { motion } from "framer-motion";

export function DocsPageLayout({ children, title, description }: { children: React.ReactNode, title: string, description?: string }) {
    return (
        <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: "easeOut" }}
            className="pb-24 pt-10"
        >
            <div className="mb-10 space-y-4">
                <h1 className="text-4xl font-semibold tracking-tight text-white">{title}</h1>
                {description && (
                    <p className="text-lg leading-7 text-neutral-400">{description}</p>
                )}
            </div>
            <div className="[&>h2]:scroll-mt-24 [&>h2]:text-2xl [&>h2]:font-semibold [&>h2]:tracking-tight [&>h2]:text-white [&>h2]:mt-12 [&>h2]:mb-8 [&>h2]:border-b [&>h2]:border-white/10 [&>h2]:pb-4 [&>h3]:scroll-mt-24 [&>h3]:text-xl [&>h3]:font-semibold [&>h3]:tracking-tight [&>h3]:text-white [&>h3]:mt-10 [&>h3]:mb-4 [&>p]:text-neutral-300 [&>p]:leading-7 [&>p:not(:last-child)]:mb-6 [&>ul]:text-neutral-300 [&>ul]:list-disc [&>ul]:pl-6 [&>ul]:mb-6 [&>ul>li]:mb-2 [&>ol]:text-neutral-300 [&>ol]:list-decimal [&>ol]:pl-6 [&>ol]:mb-6 [&>ol>li]:mb-2 [&_a]:text-[#dce85d] [&_a]:transition-colors hover:[&_a]:underline [&_strong]:text-white w-full max-w-none">
                {children}
            </div>
        </motion.div>
    );
}
