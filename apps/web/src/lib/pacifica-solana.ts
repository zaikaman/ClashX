import {
  Connection,
  PublicKey,
  SystemProgram,
  Transaction,
  TransactionInstruction,
  type Commitment,
  type TransactionSignature,
} from "@solana/web3.js";
import {
  ASSOCIATED_TOKEN_PROGRAM_ID,
  createAssociatedTokenAccountInstruction,
  getAssociatedTokenAddressSync,
  TOKEN_PROGRAM_ID,
} from "@solana/spl-token";

type BrowserSolanaWindow = Window & {
  solana?: SolanaTransactionProvider;
  phantom?: { solana?: SolanaTransactionProvider };
  solflare?: SolanaTransactionProvider;
  backpack?: { solana?: SolanaTransactionProvider };
};

export type PacificaCluster = "mainnet-beta" | "devnet";

export type PacificaSolanaConfig = {
  networkLabel: string;
  cluster: PacificaCluster;
  rpcUrl: string;
  programId: string;
  centralState: string;
  pacificaVault: string;
  pacificaFallback: string;
  collateralMint: string;
  stableCoinSymbol: string;
  supportsMint: boolean;
};

export type SolanaTransactionProvider = {
  connect: (options?: { onlyIfTrusted?: boolean }) => Promise<{ publicKey: { toString(): string } }>;
  publicKey?: { toString(): string };
  signTransaction?: (transaction: Transaction) => Promise<Transaction>;
  signAndSendTransaction?: (transaction: Transaction) => Promise<{ signature: string } | string>;
  signMessage?: (message: Uint8Array, display?: "utf8") => Promise<{ publicKey: { toString(): string }; signature: Uint8Array }>;
  isPhantom?: boolean;
  isSolflare?: boolean;
  isBackpack?: boolean;
};

const COMMITMENT: Commitment = "confirmed";
const SIX_DECIMALS = 1_000_000;
const DEPOSIT_DISCRIMINATOR = new Uint8Array([242, 35, 198, 137, 82, 225, 242, 182]);
const MINT_TEST_USDC_DISCRIMINATOR = new Uint8Array([118, 144, 78, 118, 155, 214, 185, 186]);

const MAINNET_CONFIG: PacificaSolanaConfig = {
  networkLabel: "Pacifica",
  cluster: "mainnet-beta",
  rpcUrl: process.env.NEXT_PUBLIC_SOLANA_RPC_URL || "https://api.mainnet-beta.solana.com",
  programId: "PCFA5iYgmqK6MqPhWNKg7Yv7auX7VZ4Cx7T1eJyrAMH",
  centralState: "9Gdmhq4Gv1LnNMp7aiS1HSVd7pNnXNMsbuXALCQRmGjY",
  pacificaVault: "72R843XwZxqWhsJceARQQTTbYtWy6Zw9et2YV4FpRHTa",
  pacificaFallback: "CRi2Vry6mRjPreRDJxJaJzEpguLoJ9S4o6WR7Et7Ure6",
  collateralMint: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
  stableCoinSymbol: "USDC",
  supportsMint: false,
};

const TESTNET_CONFIG: PacificaSolanaConfig = {
  networkLabel: "Devnet",
  cluster: "devnet",
  rpcUrl: process.env.NEXT_PUBLIC_SOLANA_RPC_URL || "https://api.devnet.solana.com",
  programId: "peRPsYCcB1J9jvrs29jiGdjkytxs8uHLmSPLKKP9ptm",
  centralState: "2zPRq1Qvdq5A4Ld6WsH7usgCge4ApZRYfhhf5VAjfXxv",
  pacificaVault: "5SDFdHZGTZbyRYu54CgmRkCGnPHC5pYaN27p7XGLqnBs",
  pacificaFallback: "Dz4qRHHfkH94yK1EjwN9hPKEvs3JWXYxK7J8D3TjFgpA",
  collateralMint: "USDPqRbLidFGufty2s3oizmDEKdqx7ePTqzDMbf5ZKM",
  stableCoinSymbol: "USDP",
  supportsMint: true,
};

function encodeAmount(amount: number): Uint8Array {
  const rawUnits = BigInt(Math.round(amount * SIX_DECIMALS));
  const bytes = new Uint8Array(8);
  const view = new DataView(bytes.buffer);
  view.setBigUint64(0, rawUnits, true);
  return bytes;
}

function mergeData(discriminator: Uint8Array, amount: number): Uint8Array {
  const encodedAmount = encodeAmount(amount);
  const data = new Uint8Array(discriminator.length + encodedAmount.length);
  data.set(discriminator, 0);
  data.set(encodedAmount, discriminator.length);
  return data;
}

export function getPacificaSolanaConfig(network: string): PacificaSolanaConfig {
  const normalized = network.toLowerCase();
  return normalized.includes("test") || normalized.includes("devnet") ? TESTNET_CONFIG : MAINNET_CONFIG;
}

export function getSolanaProvider(): SolanaTransactionProvider | null {
  if (typeof window === "undefined") {
    return null;
  }
  const browserWindow = window as BrowserSolanaWindow;
  return browserWindow.phantom?.solana ?? browserWindow.backpack?.solana ?? browserWindow.solflare ?? browserWindow.solana ?? null;
}

export async function connectProviderWallet(provider: SolanaTransactionProvider): Promise<string> {
  const result = await provider.connect();
  return result.publicKey.toString();
}

export function deriveUserCollateralAta(owner: PublicKey, mint: PublicKey): PublicKey {
  return getAssociatedTokenAddressSync(mint, owner, false, TOKEN_PROGRAM_ID, ASSOCIATED_TOKEN_PROGRAM_ID);
}

function deriveUserAccountPda(owner: PublicKey, programId: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync([new TextEncoder().encode("user_account"), owner.toBytes()], programId)[0];
}

function deriveEventAuthority(programId: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync([new TextEncoder().encode("__event_authority")], programId)[0];
}

async function maybeCreateAtaInstruction(connection: Connection, payer: PublicKey, owner: PublicKey, mint: PublicKey, allowOwnerOffCurve = false) {
  const ata = getAssociatedTokenAddressSync(mint, owner, allowOwnerOffCurve, TOKEN_PROGRAM_ID, ASSOCIATED_TOKEN_PROGRAM_ID);
  const info = await connection.getAccountInfo(ata, COMMITMENT);
  if (info) {
    return { ata, instruction: null as TransactionInstruction | null };
  }
  return {
    ata,
    instruction: createAssociatedTokenAccountInstruction(payer, ata, owner, mint, TOKEN_PROGRAM_ID, ASSOCIATED_TOKEN_PROGRAM_ID),
  };
}

export async function buildMintTestCollateralTransaction(
  connection: Connection,
  owner: PublicKey,
  config: PacificaSolanaConfig,
  amount: number,
): Promise<Transaction> {
  if (!config.supportsMint) {
    throw new Error("Minting test collateral is only available on Pacifica devnet.");
  }

  const programId = new PublicKey(config.programId);
  const centralState = new PublicKey(config.centralState);
  const collateralMint = new PublicKey(config.collateralMint);
  const userAccount = deriveUserAccountPda(owner, programId);
  const { ata: userCollateralAta, instruction: createAtaInstruction } = await maybeCreateAtaInstruction(connection, owner, owner, collateralMint);

  const instruction = new TransactionInstruction({
    programId,
    keys: [
      { pubkey: owner, isSigner: true, isWritable: true },
      { pubkey: userAccount, isSigner: false, isWritable: true },
      { pubkey: userCollateralAta, isSigner: false, isWritable: true },
      { pubkey: collateralMint, isSigner: false, isWritable: true },
      { pubkey: centralState, isSigner: false, isWritable: true },
      { pubkey: ASSOCIATED_TOKEN_PROGRAM_ID, isSigner: false, isWritable: false },
      { pubkey: TOKEN_PROGRAM_ID, isSigner: false, isWritable: false },
      { pubkey: SystemProgram.programId, isSigner: false, isWritable: false },
    ],
    data: Buffer.from(mergeData(MINT_TEST_USDC_DISCRIMINATOR, amount)),
  });

  const transaction = new Transaction();
  if (createAtaInstruction) {
    transaction.add(createAtaInstruction);
  }
  transaction.add(instruction);
  return transaction;
}

export async function buildDepositTransaction(
  connection: Connection,
  owner: PublicKey,
  config: PacificaSolanaConfig,
  amount: number,
): Promise<Transaction> {
  const programId = new PublicKey(config.programId);
  const centralState = new PublicKey(config.centralState);
  const collateralMint = new PublicKey(config.collateralMint);
  const eventAuthority = deriveEventAuthority(programId);
  const { ata: userCollateralAta, instruction: createUserAtaInstruction } = await maybeCreateAtaInstruction(connection, owner, owner, collateralMint);
  const pacificaVault = new PublicKey(config.pacificaVault);

  const instruction = new TransactionInstruction({
    programId,
    keys: [
      { pubkey: owner, isSigner: true, isWritable: true },
      { pubkey: userCollateralAta, isSigner: false, isWritable: true },
      { pubkey: centralState, isSigner: false, isWritable: true },
      { pubkey: pacificaVault, isSigner: false, isWritable: true },
      { pubkey: TOKEN_PROGRAM_ID, isSigner: false, isWritable: false },
      { pubkey: ASSOCIATED_TOKEN_PROGRAM_ID, isSigner: false, isWritable: false },
      { pubkey: collateralMint, isSigner: false, isWritable: false },
      { pubkey: SystemProgram.programId, isSigner: false, isWritable: false },
      { pubkey: eventAuthority, isSigner: false, isWritable: false },
      { pubkey: programId, isSigner: false, isWritable: false },
    ],
    data: Buffer.from(mergeData(DEPOSIT_DISCRIMINATOR, amount)),
  });

  const transaction = new Transaction();
  if (createUserAtaInstruction) {
    transaction.add(createUserAtaInstruction);
  }
  transaction.add(instruction);
  return transaction;
}

export async function sendWalletTransaction(
  provider: SolanaTransactionProvider,
  connection: Connection,
  owner: PublicKey,
  transaction: Transaction,
): Promise<TransactionSignature> {
  const { blockhash, lastValidBlockHeight } = await connection.getLatestBlockhash(COMMITMENT);
  transaction.feePayer = owner;
  transaction.recentBlockhash = blockhash;

  if (provider.signAndSendTransaction) {
    const result = await provider.signAndSendTransaction(transaction);
    const signature = typeof result === "string" ? result : result.signature;
    await connection.confirmTransaction({ signature, blockhash, lastValidBlockHeight }, COMMITMENT);
    return signature;
  }

  if (!provider.signTransaction) {
    throw new Error("The connected wallet cannot sign transactions.");
  }

  const signedTransaction = await provider.signTransaction(transaction);
  const signature = await connection.sendRawTransaction(signedTransaction.serialize(), { skipPreflight: false });
  await connection.confirmTransaction({ signature, blockhash, lastValidBlockHeight }, COMMITMENT);
  return signature;
}

export async function getWalletCollateralBalance(
  connection: Connection,
  ownerAddress: string,
  collateralMintAddress: string,
): Promise<number> {
  const owner = new PublicKey(ownerAddress);
  const mint = new PublicKey(collateralMintAddress);
  const ata = deriveUserCollateralAta(owner, mint);
  try {
    const balance = await connection.getTokenAccountBalance(ata, COMMITMENT);
    return Number(balance.value.uiAmount ?? 0);
  } catch {
    return 0;
  }
}

export async function getWalletGasBalance(connection: Connection, ownerAddress: string): Promise<number> {
  const lamports = await connection.getBalance(new PublicKey(ownerAddress), COMMITMENT);
  return lamports / 1_000_000_000;
}
