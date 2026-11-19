function isLoopbackUrl(value: string) {
  try {
    const hostname = new URL(value).hostname;
    return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]" || hostname === "::1";
  } catch {
    return false;
  }
}

export function isLocalDemoEnabled() {
  const chainId = Number(process.env.NEXT_PUBLIC_CHAIN_ID ?? 43113);
  const rpcUrl = process.env.NEXT_PUBLIC_RPC_URL ?? "http://127.0.0.1:8545";
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const enabled = process.env.NEXT_PUBLIC_DEMO_AUTH_ENABLED === "true";
  return enabled && chainId === 31337 && isLoopbackUrl(rpcUrl) && isLoopbackUrl(apiUrl);
}
