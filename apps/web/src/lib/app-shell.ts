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
        href: "/leaderboard",
        label: "Leaderboard",
        description: "Track the live seasonal ladder and inspect winners.",
      },
    ],
  },
  {
    label: "Build",
    items: [
      {
        href: "/build",
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
      {
        href: "/agent",
        label: "Agent desk",
        description: "Approve delegated execution safely.",
      },
    ],
  },
];

export const appWorkflow = [
  { href: "/leaderboard", label: "Study the live ladder" },
  { href: "/build", label: "Draft a strategy" },
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
    { href: "/build", label: "Open visual builder", tone: "primary" },
    { href: "/bots", label: "Open my bots", tone: "secondary" },
  ],
};

export function getAppPageMeta(pathname: string): AppPageMeta {
  const normalizedPathname = pathname !== "/" ? pathname.replace(/\/+$/, "") : pathname;

  if (normalizedPathname.startsWith("/leaderboard/")) {
    return {
      eyebrow: "Public runtime profile",
      title: "Review one live bot in detail",
      description: "Check performance, inspect recent decisions, and decide whether to follow this runtime or clone it into your own account.",
      guidanceTitle: "Use this profile",
      guidance: [
        "Start with total PnL, current streak, and drawdown so you understand the risk profile.",
        "Read recent runtime events before you mirror a strategy you do not fully understand.",
        "Use clone when you want a draft you can edit. Use follow when you want live copying.",
      ],
      actions: [
        { href: "/leaderboard", label: "Back to public board", tone: "secondary" },
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
        { href: "/agent", label: "Open agent desk", tone: "ghost" },
      ],
    };
  }

  if (normalizedPathname === "/leagues") {
    return {
      eyebrow: "Legacy route",
      title: "The seasonal leaderboard replaced leagues",
      description: "ClashX now runs on one ranked board with quarterly seasons instead of separate competitions.",
      guidanceTitle: "Use the new flow",
      guidance: [
        "Open the leaderboard to see the current season and live rankings.",
        "Use Builder studio to ship a bot that can climb the board.",
        "Open a runtime profile before you follow or clone a top performer.",
      ],
      actions: [
        { href: "/leaderboard", label: "Open leaderboard", tone: "primary" },
        { href: "/build", label: "Create a bot", tone: "secondary" },
      ],
    };
  }

  if (normalizedPathname.startsWith("/leagues/")) {
    return {
      eyebrow: "Legacy route",
      title: "Competition pages now resolve to one board",
      description: "League-specific detail pages are deprecated because rankings now live on a single seasonal leaderboard.",
      guidanceTitle: "What changed",
      guidance: [
        "The board resets into a new season every three months.",
        "Every bot competes in the same ladder instead of segmented leagues.",
        "Use runtime profiles for detail instead of league pages.",
      ],
      actions: [
        { href: "/leaderboard", label: "Open leaderboard", tone: "primary" },
        { href: "/build", label: "Create a bot", tone: "ghost" },
      ],
    };
  }

  if (normalizedPathname === "/leaderboard") {
    return {
      eyebrow: "Seasonal leaderboard",
      title: "Track the best-performing live bots",
      description: "Compare ranked runtimes, see the current season window, and decide whether to follow, clone, or outbuild the leaders.",
      guidanceTitle: "How this page helps",
      guidance: [
        "Use the season panel to see when the current ladder resets.",
        "Use the front runner cards when you want quick context on the strongest current bots.",
        "Open a runtime profile before you mirror anything so you can inspect recent behavior.",
      ],
      actions: [
        { href: "/copy", label: "Open copy center", tone: "primary" },
        { href: "/build", label: "Build your own bot", tone: "secondary" },
      ],
    };
  }

  if (normalizedPathname === "/build" || normalizedPathname === "/trade") {
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
        { href: "/leaderboard", label: "Open leaderboard", tone: "secondary" },
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
        { href: "/build", label: "New bot draft", tone: "primary" },
        { href: "/leaderboard", label: "Browse live bots", tone: "secondary" },
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
        "Open the public board if you need new bots to evaluate or follow.",
        "Use cloned drafts when you want to customize a successful idea instead of mirroring it directly.",
        "Review active follows regularly so your risk stays intentional.",
      ],
      actions: [
        { href: "/leaderboard", label: "Browse the public board", tone: "primary" },
        { href: "/bots", label: "Open my bots", tone: "secondary" },
      ],
    };
  }

  if (normalizedPathname === "/agent") {
    return {
      eyebrow: "Agent desk",
      title: "Approve delegated execution safely",
      description: "Connect the right wallet, sign the approval packet once, and keep bot execution separate from your raw signing keys.",
      guidanceTitle: "Before you approve",
      guidance: [
        "Make sure the connected browser wallet matches the wallet linked to your account.",
        "Read the status panel so you know whether you are creating a new authorization or refreshing an existing one.",
        "Return to My bots after approval when you are ready to deploy or resume a runtime.",
      ],
      actions: [
        { href: "/bots", label: "Open my bots", tone: "primary" },
        { href: "/build", label: "Create a bot", tone: "secondary" },
      ],
    };
  }

  if (normalizedPathname === "/operator/leagues") {
    return {
      eyebrow: "Legacy route",
      title: "Admin league ops were removed",
      description: "The leaderboard now advances seasons automatically every three months, so this operator desk is no longer part of the product.",
      guidanceTitle: "Use instead",
      guidance: [
        "Use the leaderboard to monitor the current season.",
        "Use bot and copy desks for operational work that still matters.",
        "Treat season boundaries as automatic rather than manually administered.",
      ],
      actions: [{ href: "/leaderboard", label: "Open leaderboard", tone: "secondary" }],
    };
  }

  return fallbackMeta;
}
