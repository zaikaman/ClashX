"use client";

import { PrivyProvider } from "@privy-io/react-auth";
import { toSolanaWalletConnectors } from "@privy-io/react-auth/solana";

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
        appearance: {
          walletChainType: "ethereum-and-solana",
          theme: "dark",
          accentColor: "#ea4c1d",
        },
        externalWallets: {
          solana: {
            // Avoid eager account restoration while wallets like Solflare are still locked.
            connectors: toSolanaWalletConnectors({ shouldAutoConnect: false }),
          },
        },
      }}
    >
      {children}
    </PrivyProvider>
  );
}
