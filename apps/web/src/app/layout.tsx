import type { Metadata } from "next";

import { ClashxPrivyProvider } from "@/components/providers/clashx-privy-provider";
import { TransitionProvider } from "@/components/providers/transition-provider";

import "@xyflow/react/dist/style.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "ClashX",
  description: "Build, deploy, and copy Pacifica-powered trading bots with a creator marketplace and transparent automation.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const privyAppId = process.env.NEXT_PUBLIC_PRIVY_APP_ID ?? process.env.PRIVY_APP_ID ?? "";

  return (
    <html lang="en">
      <body>
        <TransitionProvider>
          <ClashxPrivyProvider appId={privyAppId}>{children}</ClashxPrivyProvider>
        </TransitionProvider>
      </body>
    </html>
  );
}
