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
      {
        href: "/copilot",
        label: "Copilot",
        description: "Ask for live workspace context, private account state, and schema help.",
      },
    ],
  },
  {
    label: "Operate",
    items: [
      {
        href: "/dashboard",
        label: "Dashboard",
        description: "See live bots, open trades, and runtime alerts in one place.",
      },
      {
        href: "/analytics",
        label: "Analytics",
        description: "Compare fleet performance, exposure concentration, and action quality.",
      },
      {
        href: "/bots",
        label: "My bots",
        description: "Open drafts, runtimes, and health details.",
      },
      {
        href: "/copy",
        label: "Copy trading",
        description: "Track copied exposure, trader health, and live follow risk.",
      },
    ],
  },
];

export const appWorkflow = [
  { href: "/marketplace", label: "Browse the marketplace" },
  { href: "/builder", label: "Draft a strategy" },
  { href: "/copilot", label: "Ask Copilot for context" },
  { href: "/bots", label: "Deploy and monitor" },
  { href: "/dashboard", label: "Watch the fleet" },
  { href: "/analytics", label: "Read the analytics" },
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
        { href: "/copy", label: "Open copy trading", tone: "ghost" },
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
        { href: "/copy", label: "Open copy trading", tone: "primary" },
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

  if (normalizedPathname === "/copilot") {
    return {
      eyebrow: "Copilot",
      title: "Ask for grounded workspace context",
      description: "Use Copilot when you want live answers about your bots, account state, Pacifica readiness, or the schema behind the product.",
      guidanceTitle: "Use this desk",
      guidance: [
        "Ask direct operational questions when you want a fast answer backed by current account context.",
        "Use schema questions when you need to trace which tables hold the state behind a feature.",
        "Follow up after a summary when you want Copilot to drill into one bot, one portfolio, or one risk blocker.",
      ],
      actions: [
        { href: "/builder", label: "Open builder studio", tone: "primary" },
        { href: "/bots", label: "Open my bots", tone: "secondary" },
      ],
    };
  }

  if (normalizedPathname === "/dashboard") {
    return {
      eyebrow: "Fleet dashboard",
      title: "Monitor every bot from one control room",
      description: "Use this page to answer the operational questions fast: which bots are live, which trades are open, and which runtimes need attention now.",
      guidanceTitle: "Use this desk",
      guidance: [
        "Start with the attention queue so operational risks surface before you drill into a bot.",
        "Use the open trade radar when you need to confirm current exposure across the whole fleet.",
        "Jump into one bot only after the fleet-level board tells you where the real issue is.",
      ],
      actions: [
        { href: "/analytics", label: "Open analytics", tone: "primary" },
        { href: "/bots", label: "Open my bots", tone: "secondary" },
      ],
    };
  }

  if (normalizedPathname === "/analytics") {
    return {
      eyebrow: "Fleet analytics",
      title: "Read deeper cross-bot performance and runtime quality",
      description: "Use rankings, concentration views, and failure pressure to understand how the fleet behaves beyond the per-bot view.",
      guidanceTitle: "Use this desk",
      guidance: [
        "Read performance and exposure together so one strong bot does not hide concentrated risk elsewhere.",
        "Use the health matrix to spot runtimes that are still active but degrading quietly.",
        "Track failure pressure by reason so you fix repeated issues instead of chasing isolated events.",
      ],
      actions: [
        { href: "/dashboard", label: "Open dashboard", tone: "primary" },
        { href: "/bots", label: "Open my bots", tone: "secondary" },
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
      eyebrow: "Copy trading",
      title: "Run a live copy desk with real exposure visibility",
      description: "Track copied positions, current PnL, leader health, and execution issues from one trader-facing command center.",
      guidanceTitle: "Use this desk",
      guidance: [
        "Start with copied notional, live PnL, and open positions so you know the real book state immediately.",
        "Use the leader cards to resize, pause, or resume follows without leaving the desk.",
        "Open the advanced tab only when you actually need multi-trader basket controls.",
      ],
      actions: [
        { href: "/marketplace", label: "Browse marketplace", tone: "primary" },
        { href: "/dashboard", label: "Open operations", tone: "secondary" },
      ],
    };
  }

  return fallbackMeta;
}
