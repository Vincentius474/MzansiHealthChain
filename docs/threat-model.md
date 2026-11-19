# Threat model (hackathon scope)

What each mechanism protects, and what it does not.

| Mechanism | Protects against | Does not protect against |
|---|---|---|
| Wallet signature login | someone claiming to be a wallet they do not control | a stolen wallet key |
| JWT (1 hour) | unauthenticated API calls; session replay after expiry | a stolen token within its hour |
| One-time login nonce | replaying an old signed message | (in-memory store; resets on backend restart) |
| Smart-contract consent | access without the patient's approval; access after revoke or expiry; removed providers | a clinician who legitimately has access copying what they see |
| Provider registry (admin) | unverified wallets acting as clinicians | a dishonest or compromised admin wallet |
| AES-256-GCM per-record keys | storage-provider or database leaks of record contents; swapping a record between patients (patient bound as associated data) | compromise of the master key (env variable here; use KMS in production) |
| SHA-256 hash on-chain | silent tampering with stored records (hash checked before decrypt) | deletion of a stored record (detected, not prevented) |
| Audit log | undetected access; denied attempts are recorded too | access outside the app by someone holding the master key |
| Local Ollama for decrypted data | patient data reaching third-party AI services | a compromised host running Ollama |
| De-identification for cloud models | casual leakage of IDs, emails, phones, wallet addresses | names, addresses and free-text identifiers (needs an NER step) |
| Agents are read-only | an agent granting itself access or changing consent | prompt injection inside record text that skews a summary (output is labelled AI-generated; clinicians must verify) |

## Public by design

Everything on-chain is public: that a patient registered (pseudonymous hash), that consent was
granted to a provider address and until when, that a record exists (hash and opaque storage key),
and every audit event. No medical content is on-chain. Anyone who learns a wallet address can see
its consent and audit history, so wallets should not be linked to real names in public.

## Known gaps before real patient data

- Master key from env variable instead of KMS/HSM.
- Regex-only de-identification.
- No rate limiting or lockout on the API.
- Login nonces held in process memory.
- Text-only records; no malware scanning for future file uploads.
- No formal privacy or legal review. Health data is regulated; get review before any real use.
