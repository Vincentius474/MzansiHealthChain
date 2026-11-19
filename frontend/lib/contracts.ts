export const ADDR = {
  registry: process.env.NEXT_PUBLIC_REGISTRY_ADDR!,
  consent: process.env.NEXT_PUBLIC_CONSENT_ADDR!,
  access: process.env.NEXT_PUBLIC_ACCESS_ADDR!,
  audit: process.env.NEXT_PUBLIC_AUDIT_ADDR!,
};

/** First block to scan for events. Raise on public RPCs that limit log ranges. */
export const START_BLOCK = Number(process.env.NEXT_PUBLIC_START_BLOCK ?? 0);

export const REGISTRY_ABI = [
  "function admin() view returns (address)",
  "function registerPatient(bytes32 pseudoId)",
  "function registerLocalDemoClinician()",
  "function registerProvider(address provider, uint8 role)",
  "function roleOf(address) view returns (uint8)",
];
export const CONSENT_ABI = [
  "function grant(address provider, uint64 expiry)",
  "function revoke(address provider)",
  "function consentExpiry(address patient, address provider) view returns (uint64)",
  "event ConsentGranted(address indexed patient, address indexed provider, uint64 expiry)",
  "event ConsentRevoked(address indexed patient, address indexed provider)",
];
export const ACCESS_ABI = [
  "function addRecord(address patient, bytes32 ciphertextHash, string storageRef) returns (uint256)",
  "function canAccess(address provider, address patient) view returns (bool)",
  "function recordCount(address patient) view returns (uint256)",
  "function getOwnRecords() view returns (tuple(bytes32 ciphertextHash, string storageRef, address addedBy, uint64 timestamp)[])",
];
export const AUDIT_ABI = [
  "event AccessLogged(address indexed patient, address indexed provider, uint256 indexed recordId, bytes32 actionHash, uint64 timestamp)",
];

export const ROLE = { None: 0, Patient: 1, Clinician: 2, Facility: 3 } as const;
