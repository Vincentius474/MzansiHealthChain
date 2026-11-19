// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./Base.sol";

contract AccessControlTest is Base {
    function test_canAccess_matrix() public {
        assertFalse(acl.canAccess(doc, alice));       // registered provider, no consent
        assertFalse(acl.canAccess(stranger, alice));  // unregistered
        _grant(alice, doc, 1 days);
        assertTrue(acl.canAccess(doc, alice));
        assertFalse(acl.canAccess(doc, bob));         // consent is per patient
        assertFalse(acl.canAccess(hospital, alice));  // consent is per provider
    }

    function test_addRecord_storesAndEmits() public {
        _grant(alice, doc, 1 days);
        vm.expectEmit(true, true, true, true);
        emit AccessControl.RecordAdded(alice, 0, HASH_1, doc);
        uint256 id = _addRecord(doc, alice, HASH_1, REF_1);
        assertEq(id, 0);
        assertEq(acl.recordCount(alice), 1);

        AccessControl.Record[] memory recs = acl.getRecords(doc, alice);
        assertEq(recs.length, 1);
        assertEq(recs[0].ciphertextHash, HASH_1);
        assertEq(recs[0].storageRef, REF_1);
        assertEq(recs[0].addedBy, doc);
        assertEq(recs[0].timestamp, uint64(block.timestamp));
    }

    function test_addRecord_idsIncrementPerPatient() public {
        _grant(alice, doc, 1 days);
        _grant(bob, doc, 1 days);
        assertEq(_addRecord(doc, alice, HASH_1, REF_1), 0);
        assertEq(_addRecord(doc, alice, HASH_2, REF_2), 1);
        assertEq(_addRecord(doc, bob, HASH_1, REF_1), 0);
        assertEq(acl.recordCount(alice), 2);
        assertEq(acl.recordCount(bob), 1);
    }

    function test_addRecord_facilityCanWriteToo() public {
        _grant(alice, hospital, 1 days);
        _addRecord(hospital, alice, HASH_1, REF_1);
        assertEq(acl.recordCount(alice), 1);
    }

    function test_addRecord_revertsWithoutConsent() public {
        vm.prank(doc);
        vm.expectRevert("no consent");
        acl.addRecord(alice, HASH_1, REF_1);
    }

    function test_addRecord_revertsForUnregisteredCaller() public {
        vm.prank(stranger);
        vm.expectRevert("no consent");
        acl.addRecord(alice, HASH_1, REF_1);
    }

    function test_addRecord_patientCanWriteOwnRecords() public {
        vm.prank(alice);
        acl.addRecord(alice, HASH_1, REF_1);
        assertEq(acl.recordCount(alice), 1);
    }

    function test_addRecord_validatesInputs() public {
        _grant(alice, doc, 1 days);
        vm.startPrank(doc);
        vm.expectRevert("empty hash");
        acl.addRecord(alice, bytes32(0), REF_1);
        vm.expectRevert("bad ref length");
        acl.addRecord(alice, HASH_1, "");
        vm.expectRevert("bad ref length");
        acl.addRecord(alice, HASH_1, string(new bytes(257)));
        acl.addRecord(alice, HASH_1, string(new bytes(256))); // boundary ok
        vm.stopPrank();
        assertEq(acl.recordCount(alice), 1);
    }

    function test_addRecord_revertsAfterRevoke() public {
        _grant(alice, doc, 1 days);
        _addRecord(doc, alice, HASH_1, REF_1);
        vm.prank(alice);
        con.revoke(doc);
        vm.prank(doc);
        vm.expectRevert("no consent");
        acl.addRecord(alice, HASH_2, REF_2);
    }

    function test_addRecord_revertsAfterExpiry() public {
        _grant(alice, doc, 1 days);
        vm.warp(block.timestamp + 1 days);
        vm.prank(doc);
        vm.expectRevert("no consent");
        acl.addRecord(alice, HASH_1, REF_1);
    }

    function test_removedProviderLosesAccessImmediately() public {
        _grant(alice, doc, 30 days);
        _addRecord(doc, alice, HASH_1, REF_1);
        reg.removeProvider(doc); // consent entry still exists, registry check must block
        assertTrue(con.hasConsent(alice, doc));
        assertFalse(acl.canAccess(doc, alice));
        vm.prank(doc);
        vm.expectRevert("no consent");
        acl.addRecord(alice, HASH_2, REF_2);
        vm.expectRevert("no consent");
        acl.getRecords(doc, alice);
    }

    function test_getRecords_returnsInOrderForAnyConsentedProvider() public {
        _grant(alice, doc, 1 days);
        _grant(alice, hospital, 1 days);
        _addRecord(doc, alice, HASH_1, REF_1);
        _addRecord(hospital, alice, HASH_2, REF_2);

        AccessControl.Record[] memory viaDoc = acl.getRecords(doc, alice);
        AccessControl.Record[] memory viaHospital = acl.getRecords(hospital, alice);
        assertEq(viaDoc.length, 2);
        assertEq(viaHospital.length, 2);
        assertEq(viaDoc[0].ciphertextHash, HASH_1);
        assertEq(viaDoc[1].ciphertextHash, HASH_2);
        assertEq(viaDoc[1].addedBy, hospital);
    }

    function test_getRecords_revertsWithoutConsentOrAfterRevoke() public {
        vm.expectRevert("no consent");
        acl.getRecords(doc, alice);

        _grant(alice, doc, 1 days);
        _addRecord(doc, alice, HASH_1, REF_1);
        vm.prank(alice);
        con.revoke(doc);
        vm.expectRevert("no consent");
        acl.getRecords(doc, alice);
    }

    function test_getRecords_doesNotLeakOtherPatients() public {
        _grant(alice, doc, 1 days);
        _addRecord(doc, alice, HASH_1, REF_1);
        vm.expectRevert("no consent"); // doc has no consent from bob
        acl.getRecords(doc, bob);
    }

    function test_getOwnRecords_patientSeesOwnEvenWithoutAnyProviderConsent() public {
        _grant(alice, doc, 1 days);
        _addRecord(doc, alice, HASH_1, REF_1);
        vm.prank(alice);
        con.revoke(doc);

        vm.prank(alice);
        AccessControl.Record[] memory mine = acl.getOwnRecords();
        assertEq(mine.length, 1);
        assertEq(mine[0].ciphertextHash, HASH_1);

        vm.prank(bob);
        assertEq(acl.getOwnRecords().length, 0); // bob sees only his own
    }

    function test_getOwnRecords_revertsForNonPatients() public {
        vm.prank(doc);
        vm.expectRevert("not patient");
        acl.getOwnRecords();
        vm.prank(stranger);
        vm.expectRevert("not patient");
        acl.getOwnRecords();
    }

    function testFuzz_onlyConsentedProviderCanWrite(address caller, uint64 duration) public {
        vm.assume(caller != doc && caller != hospital && caller != alice && caller != bob && uint160(caller) > 0xFF);
        duration = uint64(bound(duration, 1, con.MAX_DURATION()));
        _grant(alice, doc, duration);
        vm.prank(caller);
        vm.expectRevert("no consent");
        acl.addRecord(alice, HASH_1, REF_1);
        _addRecord(doc, alice, HASH_1, REF_1); // the consented one still can
    }
}
