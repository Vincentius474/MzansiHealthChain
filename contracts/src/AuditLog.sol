// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title AuditLog
/// @notice Append-only access trail. Only an authorised logger (the backend relayer) can write.
///         Log denied attempts too, using `NO_RECORD` when no specific record applies.
contract AuditLog {
    uint256 public constant NO_RECORD = type(uint256).max;

    address public owner;
    mapping(address => bool) public isLogger;
    mapping(address => uint256) public auditCount; // per patient

    event AccessLogged(
        address indexed patient,
        address indexed provider,
        uint256 indexed recordId,
        bytes32 actionHash, // keccak256("SUMMARY_REQUESTED"), keccak256("ACCESS_DENIED"), ...
        uint64 timestamp
    );
    event LoggerSet(address indexed logger, bool allowed);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    constructor() {
        owner = msg.sender;
        emit OwnershipTransferred(address(0), msg.sender);
    }

    function setLogger(address who, bool allowed) external onlyOwner {
        require(who != address(0), "zero address");
        isLogger[who] = allowed;
        emit LoggerSet(who, allowed);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "zero address");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    function logAccess(address patient, address provider, uint256 recordId, bytes32 actionHash) external {
        require(isLogger[msg.sender], "not logger");
        require(patient != address(0) && provider != address(0), "zero address");
        require(actionHash != bytes32(0), "empty action");
        auditCount[patient] += 1;
        emit AccessLogged(patient, provider, recordId, actionHash, uint64(block.timestamp));
    }
}
