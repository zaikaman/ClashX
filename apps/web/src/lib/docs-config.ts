export type NavItem = {
    title: string;
    href?: string;
    items?: NavItem[];
    icon?: React.ReactNode;
};

export const docsConfig: { sidebarNav: NavItem[] } = {
    sidebarNav: [
        {
            title: "Get started",
            items: [
                { title: "Introduction", href: "/docs/introduction" },
            ],
        },
        {
            title: "Architecture & Systems",
            items: [
                { title: "Architecture", href: "/docs/architecture" },
                { title: "Rules Engine", href: "/docs/rules-engine" },
            ],
        },
        {
            title: "Product Features",
            items: [
                { title: "Visual Builder", href: "/docs/core-features/builder" },
                { title: "Runtime Engine", href: "/docs/core-features/runtime" },
                { title: "Copy Trading", href: "/docs/core-features/copy" },
                { title: "AI Copilot", href: "/docs/core-features/copilot" },
            ],
        },
        {
            title: "References",
            items: [
                { title: "API Reference", href: "/docs/api-reference" },
            ],
        },
    ],
};
