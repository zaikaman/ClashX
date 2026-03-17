import bs58 from "bs58";

export function encodeBase58(bytes: Uint8Array): string {
  return bs58.encode(Buffer.from(bytes));
}
