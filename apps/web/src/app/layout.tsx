import type { Metadata } from "next";

import { ClashxPrivyProvider } from "@/components/providers/clashx-privy-provider";

import "@xyflow/react/dist/style.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "ClashX",
  description: "Build, deploy, and copy Pacifica-powered trading bots with live leaderboards and transparent automation.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <ClashxPrivyProvider appId={process.env.PRIVY_APP_ID ?? ""}>{children}</ClashxPrivyProvider>
      </body>
    </html>
  );
}
