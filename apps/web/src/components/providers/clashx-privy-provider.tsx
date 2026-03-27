"use client";

import { PrivyProvider } from "@privy-io/react-auth";
import { toSolanaWalletConnectors } from "@privy-io/react-auth/solana";

const solanaWalletConnectors = toSolanaWalletConnectors({ shouldAutoConnect: false });

export function ClashxPrivyProvider({
  appId,
  children,
}: Readonly<{
  appId: string;
  children: React.ReactNode;
}>) {
  if (!appId) {
    throw new Error("PRIVY_APP_ID is required to render ClashX.");
  }

  return (
    <PrivyProvider
      appId={appId}
      config={{
        loginMethods: ["wallet"],
        appearance: {
          showWalletLoginFirst: true,
          walletChainType: "ethereum-and-solana",
          theme: "dark",
          accentColor: "#ea4c1d",
        },
        externalWallets: {
          walletConnect: { enabled: false },
          solana: {
            // Avoid eager account restoration while wallets like Solflare are still locked.
            connectors: solanaWalletConnectors,
          },
        },
      }}
    >
      {children}
    </PrivyProvider>
  );
}
