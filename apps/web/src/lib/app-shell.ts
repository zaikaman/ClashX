export type AppAction = {
  href: string;
  label: string;
  tone?: "primary" | "secondary" | "ghost";
};

export type AppNavItem = {
  href: string;
  label: string;
  description: string;
  match?: "exact" | "prefix";
};

export type AppNavGroup = {
  label: string;
  items: AppNavItem[];
};

export type AppPageMeta = {
  eyebrow: string;
  title: string;
  description: string;
  guidanceTitle: string;
  guidance: string[];
  actions: AppAction[];
};

export const appNavGroups: AppNavGroup[] = [
  {
    label: "Explore",
    items: [
      {
        href: "/marketplace",
        label: "Marketplace",
        description: "Discover public bots, creator shelves, and live winners.",
      },
    ],
  },
  {
    label: "Build",
    items: [
      {
        href: "/builder",
        label: "Builder studio",
        description: "Create, validate, and deploy a bot from one flow.",
      },
    ],
  },
  {
    label: "Operate",
    items: [
      {
        href: "/bots",
        label: "My bots",
        description: "Open drafts, runtimes, and health details.",
      },
      {
        href: "/copy",
        label: "Copy center",
        description: "Manage follows and cloned drafts.",
      },
    ],
  },
];

export const appWorkflow = [
  { href: "/marketplace", label: "Browse the marketplace" },
  { href: "/builder", label: "Draft a strategy" },
  { href: "/bots", label: "Deploy and monitor" },
  { href: "/copy", label: "Follow or clone a winner" },
];

function isRouteMatch(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function isNavItemActive(pathname: string, item: AppNavItem) {
  return item.match === "exact" ? pathname === item.href : isRouteMatch(pathname, item.href);
}

const fallbackMeta: AppPageMeta = {
  eyebrow: "Workspace",
  title: "Control deck",
  description: "Move between discovery, building, and runtime operations from one place.",
  guidanceTitle: "Recommended flow",
  guidance: [
    "Use the left sidebar to move between the main desks.",
    "Open the page action buttons when you want the next logical step.",
    "Return to My bots whenever you want runtime health or controls.",
  ],
  actions: [
    { href: "/builder", label: "Open visual builder", tone: "primary" },
    { href: "/bots", label: "Open my bots", tone: "secondary" },
  ],
};

export function getAppPageMeta(pathname: string): AppPageMeta {
  const normalizedPathname = pathname !== "/" ? pathname.replace(/\/+$/, "") : pathname;

  if (normalizedPathname.startsWith("/marketplace/")) {
    return {
      eyebrow: "Marketplace profile",
      title: "Review one live bot in detail",
      description: "Check performance, inspect recent decisions, and decide whether to follow this runtime or clone it into your own account.",
      guidanceTitle: "Use this profile",
      guidance: [
        "Start with total PnL, current streak, and drawdown so you understand the risk profile.",
        "Read recent runtime events before you mirror a strategy you do not fully understand.",
        "Use clone when you want a draft you can edit. Use follow when you want live copying.",
      ],
      actions: [
        { href: "/marketplace", label: "Back to marketplace", tone: "secondary" },
        { href: "/copy", label: "Open copy center", tone: "ghost" },
      ],
    };
  }

  if (normalizedPathname.startsWith("/bots/")) {
    return {
      eyebrow: "Bot runtime",
      title: "Operate one bot with confidence",
      description: "This desk is for runtime health, failure recovery, advanced settings, and the execution log for a single bot.",
      guidanceTitle: "What to check first",
      guidance: [
        "Confirm the runtime status before you change anything else.",
        "Read health and failure panels to understand whether the bot is blocked or unhealthy.",
        "Use the execution log to verify what the bot actually decided, not just what it was supposed to do.",
      ],
      actions: [
        { href: "/bots", label: "Back to my bots", tone: "secondary" },
        { href: "/builder", label: "Open builder studio", tone: "ghost" },
      ],
    };
  }

  if (normalizedPathname === "/marketplace") {
    return {
      eyebrow: "Creator marketplace",
      title: "Discover the strongest live bots",
      description: "Compare ranked runtimes, creator shelves, and trust signals so you can follow, clone, or outbuild the leaders.",
      guidanceTitle: "How this page helps",
      guidance: [
        "Use featured shelves when you want curated strategy groupings instead of a raw list.",
        "Use the front runner cards when you want quick context on the strongest current bots.",
        "Open a runtime profile before you mirror anything so you can inspect recent behavior.",
      ],
      actions: [
        { href: "/copy", label: "Open copy center", tone: "primary" },
        { href: "/builder", label: "Build your own bot", tone: "secondary" },
      ],
    };
  }

  if (normalizedPathname === "/builder" || normalizedPathname === "/build") {
    return {
      eyebrow: "Builder studio",
      title: "Build a bot step by step",
      description: "Define the rule set, validate the setup, save the draft, and deploy without needing to write code.",
      guidanceTitle: "Builder flow",
      guidance: [
        "Start with the bot identity so the draft is easy to recognize later.",
        "Keep the rule set small at first. You can add more sophistication after the first draft works.",
        "Save before deploying so you always have a draft to return to in My bots.",
      ],
      actions: [
        { href: "/bots", label: "Open my bots", tone: "primary" },
        { href: "/marketplace", label: "Open marketplace", tone: "secondary" },
      ],
    };
  }

  if (normalizedPathname === "/bots") {
    return {
      eyebrow: "My bots",
      title: "Manage your full bot fleet",
      description: "See every saved bot, continue drafts, and jump into runtime controls from one cleaner index.",
      guidanceTitle: "Use this desk",
      guidance: [
        "Treat this as your control room for every bot you own.",
        "Open a runtime when you need health checks, controls, or execution history.",
        "Create new bots from Builder studio, then return here to operate them.",
      ],
      actions: [
        { href: "/builder", label: "New bot draft", tone: "primary" },
        { href: "/marketplace", label: "Browse marketplace", tone: "secondary" },
      ],
    };
  }

  if (normalizedPathname === "/copy") {
    return {
      eyebrow: "Copy center",
      title: "Manage follows and cloned drafts",
      description: "Keep track of the bots you follow live, stop a follow when needed, and reopen cloned bots for editing.",
      guidanceTitle: "Use this desk",
      guidance: [
        "Open the marketplace if you need new bots to evaluate or follow.",
        "Use cloned drafts when you want to customize a successful idea instead of mirroring it directly.",
        "Review active follows regularly so your risk stays intentional.",
      ],
      actions: [
        { href: "/marketplace", label: "Browse marketplace", tone: "primary" },
        { href: "/bots", label: "Open my bots", tone: "secondary" },
      ],
    };
  }

  return fallbackMeta;
}
