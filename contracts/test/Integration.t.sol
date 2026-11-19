// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./Base.sol";

/// End-to-end story that mirrors the sequence diagram:
/// consent -> record added -> clinician read -> audit -> revoke -> denied -> audit.
contract IntegrationTest is Base {
    bytes32 internal constant READ = keccak256("SUMMARY_REQUESTED");
    bytes32 internal constant DENIED = keccak256("ACCESS_DENIED");

    function test_fullLifecycle() public {
        // 1. Patient consents for 7 days
        _grant(alice, doc, 7 days);

        // 2. Clinician adds a record and later reads it
        _addRecord(doc, alice, HASH_1, REF_1);
        assertTrue(acl.canAccess(doc, alice));
        AccessControl.Record[] memory recs = acl.getRecords(doc, alice);
        assertEq(recs[0].storageRef, REF_1);

        // 3. Backend relayer logs the read
        vm.prank(relayer);
        audit.logAccess(alice, doc, 0, READ);
        assertEq(audit.auditCount(alice), 1);

        // 4. Patient revokes; reads and writes are now blocked
        vm.prank(alice);
        con.revoke(doc);
        assertFalse(acl.canAccess(doc, alice));
        vm.expectRevert("no consent");
        acl.getRecords(doc, alice);

        // 5. Backend logs the denied attempt
        uint256 none = audit.NO_RECORD(); // read before pranking: prank covers only the next call
        vm.prank(relayer);
        audit.logAccess(alice, doc, none, DENIED);
        assertEq(audit.auditCount(alice), 2);

        // 6. Patient can still see their own record references
        vm.prank(alice);
        assertEq(acl.getOwnRecords().length, 1);
    }

    function test_expiryBlocksWithoutAnyTransaction() public {
        _grant(alice, doc, 1 days);
        _addRecord(doc, alice, HASH_1, REF_1);
        vm.warp(block.timestamp + 1 days + 1);
        assertFalse(acl.canAccess(doc, alice));
    }

    function test_twoPatientsTwoProvidersStayIsolated() public {
        _grant(alice, doc, 1 days);
        _grant(bob, hospital, 1 days);
        _addRecord(doc, alice, HASH_1, REF_1);
        _addRecord(hospital, bob, HASH_2, REF_2);

        assertTrue(acl.canAccess(doc, alice));
        assertTrue(acl.canAccess(hospital, bob));
        assertFalse(acl.canAccess(doc, bob));
        assertFalse(acl.canAccess(hospital, alice));

        vm.expectRevert("no consent");
        acl.getRecords(doc, bob);
        vm.expectRevert("no consent");
        acl.getRecords(hospital, alice);
    }

    function test_backendRelayerHasNoPowerOverConsentOrRecords() public {
        // The relayer key is the only credential the backend holds on-chain.
        vm.startPrank(relayer);
        vm.expectRevert("not patient");
        con.grant(doc, uint64(block.timestamp + 1 days));
        vm.expectRevert("no consent");
        acl.addRecord(alice, HASH_1, REF_1);
        vm.expectRevert("not admin");
        reg.registerProvider(relayer, PatientRegistry.Role.Clinician);
        vm.stopPrank();
    }
}
