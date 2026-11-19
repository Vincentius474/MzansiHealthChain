// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./Base.sol";

contract ConsentManagementTest is Base {
    function test_grant_setsExpiryAndEmits() public {
        uint64 expiry = uint64(block.timestamp + 7 days);
        vm.expectEmit(true, true, false, true);
        emit ConsentManagement.ConsentGranted(alice, doc, expiry);
        vm.prank(alice);
        con.grant(doc, expiry);

        assertEq(con.consentExpiry(alice, doc), expiry);
        assertTrue(con.hasConsent(alice, doc));
    }

    function test_grant_revertsForNonPatients() public {
        uint64 expiry = uint64(block.timestamp + 1 days);
        vm.prank(stranger);
        vm.expectRevert("not patient");
        con.grant(doc, expiry);

        vm.prank(doc); // providers cannot grant themselves access
        vm.expectRevert("not patient");
        con.grant(doc, expiry);
    }

    function test_grant_revertsForNonProviderTarget() public {
        vm.prank(alice);
        vm.expectRevert("not provider");
        con.grant(stranger, uint64(block.timestamp + 1 days));

        vm.prank(alice);
        vm.expectRevert("not provider");
        con.grant(bob, uint64(block.timestamp + 1 days)); // patient to patient
    }

    function test_grant_revertsOnPastOrCurrentExpiry() public {
        vm.startPrank(alice);
        vm.expectRevert("expiry in past");
        con.grant(doc, uint64(block.timestamp));
        vm.warp(10 days);
        vm.expectRevert("expiry in past");
        con.grant(doc, uint64(block.timestamp - 1));
        vm.stopPrank();
    }

    function test_grant_revertsBeyondMaxDuration() public {
        vm.startPrank(alice);
        con.grant(doc, uint64(block.timestamp + con.MAX_DURATION())); // boundary ok
        uint64 tooFar = uint64(block.timestamp + con.MAX_DURATION() + 1);
        vm.expectRevert("expiry too far");
        con.grant(doc, tooFar);
        vm.stopPrank();
    }

    function test_grant_canExtendAndShorten() public {
        _grant(alice, doc, 10 days);
        _grant(alice, doc, 1 days);
        assertEq(con.consentExpiry(alice, doc), uint64(block.timestamp + 1 days));
    }

    function test_hasConsent_expiresExactlyAtExpiry() public {
        uint256 start = block.timestamp;
        _grant(alice, doc, 1 days);
        vm.warp(start + 1 days - 1);
        assertTrue(con.hasConsent(alice, doc));
        vm.warp(start + 1 days);
        assertFalse(con.hasConsent(alice, doc));
    }

    function test_revoke_clearsAndEmits() public {
        _grant(alice, doc, 1 days);
        vm.expectEmit(true, true, false, false);
        emit ConsentManagement.ConsentRevoked(alice, doc);
        vm.prank(alice);
        con.revoke(doc);
        assertEq(con.consentExpiry(alice, doc), 0);
        assertFalse(con.hasConsent(alice, doc));
    }

    function test_revoke_guards() public {
        vm.prank(stranger);
        vm.expectRevert("not patient");
        con.revoke(doc);

        vm.prank(alice);
        vm.expectRevert("no consent");
        con.revoke(doc);

        _grant(alice, doc, 1 days);
        vm.prank(alice);
        con.revoke(doc);
        vm.prank(alice);
        vm.expectRevert("no consent"); // cannot revoke twice
        con.revoke(doc);
    }

    function test_otherPartiesCannotRevokeMyConsent() public {
        _grant(alice, doc, 1 days);
        vm.prank(bob); // bob revoking only touches bob's own mapping
        vm.expectRevert("no consent");
        con.revoke(doc);
        vm.prank(doc);
        vm.expectRevert("not patient");
        con.revoke(doc);
        assertTrue(con.hasConsent(alice, doc));
    }

    function test_regrantAfterRevoke() public {
        _grant(alice, doc, 1 days);
        vm.prank(alice);
        con.revoke(doc);
        _grant(alice, doc, 2 days);
        assertTrue(con.hasConsent(alice, doc));
    }

    function test_consentIsPerProviderAndPerPatient() public {
        _grant(alice, doc, 1 days);
        assertTrue(con.hasConsent(alice, doc));
        assertFalse(con.hasConsent(alice, hospital)); // other provider
        assertFalse(con.hasConsent(bob, doc));        // other patient
    }

    function testFuzz_grantWindow(uint64 duration) public {
        duration = uint64(bound(duration, 1, con.MAX_DURATION()));
        uint64 expiry = uint64(block.timestamp) + duration;
        vm.prank(alice);
        con.grant(doc, expiry);
        assertTrue(con.hasConsent(alice, doc));
        vm.warp(expiry);
        assertFalse(con.hasConsent(alice, doc));
    }
}
