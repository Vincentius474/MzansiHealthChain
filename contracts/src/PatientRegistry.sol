// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title PatientRegistry
/// @notice Registers patient wallets (pseudonymous ID only) and admin-verified providers.
/// @dev No personal data is stored. `pseudoId` must be a salted hash computed off-chain.
contract PatientRegistry {
    enum Role { None, Patient, Clinician, Facility }

    address public admin;
    mapping(address => Role) public roleOf;
    mapping(address => bytes32) public pseudoIdOf;
    mapping(bytes32 => bool) public pseudoIdTaken;

    event PatientRegistered(address indexed patient, bytes32 pseudoId);
    event ProviderRegistered(address indexed provider, Role role);
    event ProviderRemoved(address indexed provider);
    event AdminTransferred(address indexed previousAdmin, address indexed newAdmin);

    modifier onlyAdmin() {
        require(msg.sender == admin, "not admin");
        _;
    }

    constructor() {
        admin = msg.sender;
        emit AdminTransferred(address(0), msg.sender);
    }

    /// @notice A wallet registers itself as a patient.
    function registerPatient(bytes32 pseudoId) external {
        require(pseudoId != bytes32(0), "empty pseudoId");
        require(roleOf[msg.sender] == Role.None, "already registered");
        require(!pseudoIdTaken[pseudoId], "pseudoId taken");
        roleOf[msg.sender] = Role.Patient;
        pseudoIdOf[msg.sender] = pseudoId;
        pseudoIdTaken[pseudoId] = true;
        emit PatientRegistered(msg.sender, pseudoId);
    }

    /// @notice Lets local Anvil demo wallets self-register as clinicians.
    function registerLocalDemoClinician() external {
        require(block.chainid == 31337, "local demo only");
        require(roleOf[msg.sender] == Role.None, "already registered");
        roleOf[msg.sender] = Role.Clinician;
        emit ProviderRegistered(msg.sender, Role.Clinician);
    }

    /// @notice Admin registers a verified clinician or facility (credential check happens off-chain).
    function registerProvider(address provider, Role role) external onlyAdmin {
        require(provider != address(0), "zero address");
        require(role == Role.Clinician || role == Role.Facility, "bad role");
        require(roleOf[provider] == Role.None, "already registered");
        roleOf[provider] = role;
        emit ProviderRegistered(provider, role);
    }

    /// @notice Admin removes a provider. All their access stops immediately because
    ///         AccessControl.canAccess re-checks the registry on every call.
    function removeProvider(address provider) external onlyAdmin {
        require(isProvider(provider), "not a provider");
        roleOf[provider] = Role.None;
        emit ProviderRemoved(provider);
    }

    function transferAdmin(address newAdmin) external onlyAdmin {
        require(newAdmin != address(0), "zero address");
        emit AdminTransferred(admin, newAdmin);
        admin = newAdmin;
    }

    function isPatient(address a) external view returns (bool) {
        return roleOf[a] == Role.Patient;
    }

    function isProvider(address a) public view returns (bool) {
        Role r = roleOf[a];
        return r == Role.Clinician || r == Role.Facility;
    }
}
