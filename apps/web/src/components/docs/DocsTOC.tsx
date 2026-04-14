"use client";

import { useEffect, useState } from "react";

export function DocsTOC() {
    const [headings, setHeadings] = useState<{ id: string; text: string; level: number }[]>([]);
    const [activeId, setActiveId] = useState<string>("");

    useEffect(() => {
        const elements = Array.from(document.querySelectorAll("h2, h3"))
            .map((element) => {
                if (!element.id) {
                    element.id = element.textContent?.toLowerCase().replace(/[^a-z0-9]+/g, "-") || "";
                }
                return {
                    id: element.id,
                    text: element.textContent || "",
                    level: Number(element.tagName.replace("H", ""))
                };
            })
            .filter((h) => h.id);

        setHeadings(elements);

        const observer = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting) {
                        setActiveId(entry.target.id);
                    }
                });
            },
            { rootMargin: "0% 0% -80% 0%" }
        );

        document.querySelectorAll("h2, h3").forEach((h) => observer.observe(h));
        return () => observer.disconnect();
    }, []);

    if (headings.length === 0) return null;

    return (
        <div className="sticky top-24 pt-10">
            <h4 className="mb-4 text-sm font-semibold text-white">On this page</h4>
            <ul className="space-y-2.5 text-sm my-0 list-none pl-0">
                {headings.map((heading) => (
                    <li key={heading.id} className={heading.level === 3 ? "pl-4" : ""}>
                        <a
                            href={`#${heading.id}`}
                            className={`block transition-colors ${activeId === heading.id
                                    ? "text-[#dce85d] font-medium"
                                    : "text-neutral-500 hover:text-neutral-300"
                                }`}
                        >
                            {heading.text}
                        </a>
                    </li>
                ))}
            </ul>
        </div>
    );
}
