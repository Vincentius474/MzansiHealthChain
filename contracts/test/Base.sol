// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import {PatientRegistry} from "../src/PatientRegistry.sol";
import {ConsentManagement} from "../src/ConsentManagement.sol";
import {AccessControl} from "../src/AccessControl.sol";
import {AuditLog} from "../src/AuditLog.sol";

/// Shared fixture: one deployment, named actors, and helper shortcuts.
/// The test contract itself is the admin/deployer.
abstract contract Base is Test {
    PatientRegistry internal reg;
    ConsentManagement internal con;
    AccessControl internal acl;
    AuditLog internal audit;

    address internal alice = makeAddr("alice");         // patient
    address internal bob = makeAddr("bob");             // patient
    address internal doc = makeAddr("doc");             // clinician
    address internal hospital = makeAddr("hospital");   // facility
    address internal stranger = makeAddr("stranger");   // unregistered
    address internal relayer = makeAddr("relayer");     // audit logger

    bytes32 internal constant ALICE_ID = keccak256("alice-id");
    bytes32 internal constant BOB_ID = keccak256("bob-id");
    bytes32 internal constant HASH_1 = keccak256("ciphertext-1");
    bytes32 internal constant HASH_2 = keccak256("ciphertext-2");
    string internal constant REF_1 = "ehr/aaaa";
    string internal constant REF_2 = "ehr/bbbb";

    function setUp() public virtual {
        reg = new PatientRegistry();
        con = new ConsentManagement(reg);
        acl = new AccessControl(reg, con);
        audit = new AuditLog();

        audit.setLogger(relayer, true);
        reg.registerProvider(doc, PatientRegistry.Role.Clinician);
        reg.registerProvider(hospital, PatientRegistry.Role.Facility);

        vm.prank(alice);
        reg.registerPatient(ALICE_ID);
        vm.prank(bob);
        reg.registerPatient(BOB_ID);
    }

    function _grant(address patient, address provider, uint256 duration) internal {
        vm.prank(patient);
        con.grant(provider, uint64(block.timestamp + duration));
    }

    function _addRecord(address provider, address patient, bytes32 h, string memory ref)
        internal
        returns (uint256 id)
    {
        vm.prank(provider);
        id = acl.addRecord(patient, h, ref);
    }
}
