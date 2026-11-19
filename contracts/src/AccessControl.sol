// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {PatientRegistry} from "./PatientRegistry.sol";
import {ConsentManagement} from "./ConsentManagement.sol";

/// @title AccessControl
/// @notice Stores only references to encrypted records: ciphertext hash + opaque storage key.
/// @dev Everything on-chain is public. Hashes and refs reveal that a record exists, never its
///      content. `getRecords` takes `provider` explicitly so the backend can check access on
///      behalf of a signed-in clinician; this is a policy gate, not a secrecy guarantee.
contract AccessControl {
    uint256 public constant MAX_REF_LENGTH = 256;

    struct Record {
        bytes32 ciphertextHash; // SHA-256 of the encrypted blob
        string storageRef;      // object key in storage (opaque)
        address addedBy;
        uint64 timestamp;
    }

    PatientRegistry public immutable registry;
    ConsentManagement public immutable consent;
    mapping(address => Record[]) private _records;

    event RecordAdded(
        address indexed patient,
        uint256 indexed recordId,
        bytes32 ciphertextHash,
        address indexed by
    );

    constructor(PatientRegistry r, ConsentManagement c) {
        registry = r;
        consent = c;
    }

    /// @notice Returns whether a registered provider has active consent from the patient.
    function canAccess(address provider, address patient) public view returns (bool) {
        return registry.isProvider(provider) && consent.hasConsent(patient, provider);
    }

    /// @notice Patients can add their own records; providers need active patient consent.
    function addRecord(address patient, bytes32 ciphertextHash, string calldata storageRef)
        external
        returns (uint256 id)
    {
        require(
            (msg.sender == patient && registry.isPatient(patient)) || canAccess(msg.sender, patient),
            "no consent"
        );
        require(ciphertextHash != bytes32(0), "empty hash");
        uint256 len = bytes(storageRef).length;
        require(len > 0 && len <= MAX_REF_LENGTH, "bad ref length");

        _records[patient].push(Record(ciphertextHash, storageRef, msg.sender, uint64(block.timestamp)));
        id = _records[patient].length - 1;
        emit RecordAdded(patient, id, ciphertextHash, msg.sender);
    }

    function getRecords(address provider, address patient) external view returns (Record[] memory) {
        require(canAccess(provider, patient), "no consent");
        return _records[patient];
    }

    /// @notice A patient reads the references to their own records (call from the patient wallet).
    function getOwnRecords() external view returns (Record[] memory) {
        require(registry.isPatient(msg.sender), "not patient");
        return _records[msg.sender];
    }

    function recordCount(address patient) external view returns (uint256) {
        return _records[patient].length;
    }
}
