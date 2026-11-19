import { BrowserProvider, Contract, JsonRpcSigner, id } from "ethers";
import { ADDR, REGISTRY_ABI, ROLE } from "./contracts";
import { isLocalDemoEnabled } from "./demo";

const CHAIN_ID = Number(process.env.NEXT_PUBLIC_CHAIN_ID ?? 43113);

const CHAINS: Record<number, any> = {
  43114: {
    chainName: "Avalanche C-Chain",
    nativeCurrency: { name: "AVAX", symbol: "AVAX", decimals: 18 },
    rpcUrls: [process.env.NEXT_PUBLIC_RPC_URL ?? "https://api.avax.network/ext/bc/C/rpc"],
    blockExplorerUrls: ["https://explorer.avax.network/c-chain"],
  },
  43113: {
    chainName: "Avalanche Fuji C-Chain",
    nativeCurrency: { name: "AVAX", symbol: "AVAX", decimals: 18 },
    rpcUrls: [process.env.NEXT_PUBLIC_RPC_URL ?? "https://api.avax-test.network/ext/bc/C/rpc"],
    blockExplorerUrls: ["https://explorer-test.avax.network/c-chain"],
  },
  31337: {
    chainName: "Local Anvil",
    nativeCurrency: { name: "ETH", symbol: "ETH", decimals: 18 },
    rpcUrls: [process.env.NEXT_PUBLIC_RPC_URL ?? "http://127.0.0.1:8545"],
  },
};

declare global {
  interface Window { avalanche?: any; ethereum?: any }
}

/** Core Wallet injects window.avalanche (EIP-1193). Fall back to window.ethereum. */
function injected() {
  const p = window.avalanche ?? window.ethereum;
  if (!p) throw new Error("No compatible browser wallet was found. Install Core Wallet or MetaMask and try again.");
  return p;
}

export function hasWalletExtension() {
  return typeof window !== "undefined" && Boolean(window.avalanche ?? window.ethereum);
}

export async function connect(): Promise<JsonRpcSigner> {
  const p = injected();
  await p.request({ method: "eth_requestAccounts" });
  const hexId = "0x" + CHAIN_ID.toString(16);
  try {
    await p.request({ method: "wallet_switchEthereumChain", params: [{ chainId: hexId }] });
  } catch (e: any) {
    if (e.code === 4902 || e.code === -32603)
      await p.request({ method: "wallet_addEthereumChain", params: [{ chainId: hexId, ...CHAINS[CHAIN_ID] }] });
    else throw e;
  }
  return new BrowserProvider(p).getSigner();
}

export async function assertRegistryDeployed(signer: JsonRpcSigner) {
  const code = await signer.provider.getCode(ADDR.registry);
  if (code === "0x") {
    throw new Error("No PatientRegistry contract is deployed at the configured address on the selected network.");
  }
}

export async function ensureDemoRequesterRegistered(signer: JsonRpcSigner) {
  await assertRegistryDeployed(signer);
  const registry = new Contract(ADDR.registry, REGISTRY_ABI, signer);
  const role = Number(await registry.roleOf(await signer.getAddress()));
  if (role === ROLE.Clinician) return;
  if (role !== ROLE.None) {
    const roleName = role === ROLE.Patient ? "data owner" : "another provider role";
    throw new Error(`This wallet is already registered as ${roleName}. Use a different wallet for the data requester account.`);
  }
  if (!isLocalDemoEnabled()) {
    throw new Error("This wallet is not registered as a clinician. Ask the registry administrator to register it.");
  }
  const tx = await registry.registerLocalDemoClinician();
  await tx.wait();
}


export async function registerPatientWallet(signer: JsonRpcSigner) {
  await assertRegistryDeployed(signer);

  const registry = new Contract(ADDR.registry, REGISTRY_ABI, signer);
  const patientAddress = await signer.getAddress();

  const role = Number(await registry.roleOf(patientAddress));

  if (role === ROLE.Patient) {
    return null; // Already registered; continue wallet linking.
  }

  if (role !== ROLE.None) {
    throw new Error("This wallet already has another registry role. Use a patient wallet.");
  }

  const randomId = crypto.randomUUID();
  const pseudoId = id(randomId);

  const tx = await registry.registerPatient(pseudoId);
  await tx.wait();

  return tx.hash;
}

