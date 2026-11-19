// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./Base.sol";

contract AuditLogTest is Base {
    bytes32 internal constant ACTION = keccak256("SUMMARY_REQUESTED");

    function test_ownerIsDeployerAndRelayerIsLogger() public {
        assertEq(audit.owner(), address(this));
        assertTrue(audit.isLogger(relayer));
        assertFalse(audit.isLogger(stranger));
    }

    function test_logAccess_emitsAndCounts() public {
        vm.expectEmit(true, true, true, true);
        emit AuditLog.AccessLogged(alice, doc, 3, ACTION, uint64(block.timestamp));
        vm.prank(relayer);
        audit.logAccess(alice, doc, 3, ACTION);

        assertEq(audit.auditCount(alice), 1);
        assertEq(audit.auditCount(bob), 0);

        vm.prank(relayer);
        audit.logAccess(alice, doc, 4, ACTION);
        assertEq(audit.auditCount(alice), 2);
    }

    function test_logAccess_canRecordDeniedAttemptsWithoutRecordId() public {
        bytes32 denied = keccak256("ACCESS_DENIED");
        uint256 none = audit.NO_RECORD();
        vm.expectEmit(true, true, true, true);
        emit AuditLog.AccessLogged(alice, stranger, none, denied, uint64(block.timestamp));
        vm.prank(relayer);
        audit.logAccess(alice, stranger, none, denied);
    }

    function test_logAccess_onlyLoggers() public {
        vm.prank(stranger);
        vm.expectRevert("not logger");
        audit.logAccess(alice, doc, 0, ACTION);

        vm.prank(doc); // providers cannot write their own audit entries
        vm.expectRevert("not logger");
        audit.logAccess(alice, doc, 0, ACTION);

        vm.prank(alice); // neither can patients
        vm.expectRevert("not logger");
        audit.logAccess(alice, doc, 0, ACTION);
    }

    function test_logAccess_validatesInputs() public {
        vm.startPrank(relayer);
        vm.expectRevert("zero address");
        audit.logAccess(address(0), doc, 0, ACTION);
        vm.expectRevert("zero address");
        audit.logAccess(alice, address(0), 0, ACTION);
        vm.expectRevert("empty action");
        audit.logAccess(alice, doc, 0, bytes32(0));
        vm.stopPrank();
    }

    function test_setLogger_ownerOnlyAndRevocable() public {
        vm.prank(stranger);
        vm.expectRevert("not owner");
        audit.setLogger(stranger, true);

        vm.expectEmit(true, false, false, true);
        emit AuditLog.LoggerSet(stranger, true);
        audit.setLogger(stranger, true);
        vm.prank(stranger);
        audit.logAccess(alice, doc, 0, ACTION);

        audit.setLogger(stranger, false);
        vm.prank(stranger);
        vm.expectRevert("not logger");
        audit.logAccess(alice, doc, 0, ACTION);
    }

    function test_setLogger_rejectsZeroAddress() public {
        vm.expectRevert("zero address");
        audit.setLogger(address(0), true);
    }

    function test_transferOwnership() public {
        audit.transferOwnership(alice);
        assertEq(audit.owner(), alice);

        vm.expectRevert("not owner"); // previous owner locked out
        audit.setLogger(stranger, true);
        vm.prank(alice);
        audit.setLogger(stranger, true);
    }

    function test_transferOwnership_guards() public {
        vm.prank(stranger);
        vm.expectRevert("not owner");
        audit.transferOwnership(stranger);
        vm.expectRevert("zero address");
        audit.transferOwnership(address(0));
    }
}
