// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {PatientRegistry} from "./PatientRegistry.sol";

/// @title ConsentManagement
/// @notice Patients grant and revoke provider access. Only the patient's own wallet can change
///         their consent; neither the backend, the AI agent nor the admin can.
contract ConsentManagement {
    uint64 public constant MAX_DURATION = 365 days;

    PatientRegistry public immutable registry;
    /// patient => provider => unix expiry (0 = no consent)
    mapping(address => mapping(address => uint64)) public consentExpiry;

    event ConsentGranted(address indexed patient, address indexed provider, uint64 expiry);
    event ConsentRevoked(address indexed patient, address indexed provider);

    constructor(PatientRegistry r) {
        registry = r;
    }

    function grant(address provider, uint64 expiry) external {
        require(registry.isPatient(msg.sender), "not patient");
        require(registry.isProvider(provider), "not provider");
        require(expiry > block.timestamp, "expiry in past");
        require(expiry <= block.timestamp + MAX_DURATION, "expiry too far");
        consentExpiry[msg.sender][provider] = expiry;
        emit ConsentGranted(msg.sender, provider, expiry);
    }

    function revoke(address provider) external {
        require(registry.isPatient(msg.sender), "not patient");
        require(consentExpiry[msg.sender][provider] != 0, "no consent");
        consentExpiry[msg.sender][provider] = 0;
        emit ConsentRevoked(msg.sender, provider);
    }

    /// @notice True while the patient's grant to `provider` has not expired.
    function hasConsent(address patient, address provider) public view returns (bool) {
        return consentExpiry[patient][provider] > block.timestamp;
    }
}
