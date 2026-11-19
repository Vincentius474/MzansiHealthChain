// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./Base.sol";

contract PatientRegistryTest is Base {
    function test_adminIsDeployer() public {
        assertEq(reg.admin(), address(this));
    }

    function test_registerPatient_storesRoleAndId() public {
        assertEq(uint8(reg.roleOf(alice)), uint8(PatientRegistry.Role.Patient));
        assertEq(reg.pseudoIdOf(alice), ALICE_ID);
        assertTrue(reg.pseudoIdTaken(ALICE_ID));
        assertTrue(reg.isPatient(alice));
        assertFalse(reg.isProvider(alice));
    }

    function test_registerPatient_emitsEvent() public {
        address carol = makeAddr("carol");
        vm.expectEmit(true, false, false, true);
        emit PatientRegistry.PatientRegistered(carol, keccak256("carol-id"));
        vm.prank(carol);
        reg.registerPatient(keccak256("carol-id"));
    }

    function test_registerPatient_revertsOnZeroId() public {
        vm.prank(stranger);
        vm.expectRevert("empty pseudoId");
        reg.registerPatient(bytes32(0));
    }

    function test_registerPatient_revertsWhenAlreadyRegistered() public {
        vm.prank(alice);
        vm.expectRevert("already registered");
        reg.registerPatient(keccak256("another"));
    }

    function test_registerPatient_revertsOnDuplicatePseudoId() public {
        vm.prank(stranger);
        vm.expectRevert("pseudoId taken");
        reg.registerPatient(ALICE_ID);
    }

    function test_registerLocalDemoClinician_setsRoleOnAnvil() public {
        address requester = makeAddr("requester");
        vm.chainId(31337);
        vm.expectEmit(true, false, false, true);
        emit PatientRegistry.ProviderRegistered(requester, PatientRegistry.Role.Clinician);
        vm.prank(requester);
        reg.registerLocalDemoClinician();
        assertEq(uint8(reg.roleOf(requester)), uint8(PatientRegistry.Role.Clinician));
    }

    function test_registerLocalDemoClinician_revertsOffAnvil() public {
        vm.chainId(43113);
        vm.prank(stranger);
        vm.expectRevert("local demo only");
        reg.registerLocalDemoClinician();
    }

    function test_registerLocalDemoClinician_revertsForRegisteredWallet() public {
        vm.chainId(31337);
        vm.prank(alice);
        vm.expectRevert("already registered");
        reg.registerLocalDemoClinician();
    }

    function test_provider_cannotAlsoRegisterAsPatient() public {
        vm.prank(doc);
        vm.expectRevert("already registered");
        reg.registerPatient(keccak256("doc-as-patient"));
    }

    function test_registerProvider_setsRolesAndEmits() public {
        address nurse = makeAddr("nurse");
        vm.expectEmit(true, false, false, true);
        emit PatientRegistry.ProviderRegistered(nurse, PatientRegistry.Role.Clinician);
        reg.registerProvider(nurse, PatientRegistry.Role.Clinician);
        assertTrue(reg.isProvider(nurse));
        assertEq(uint8(reg.roleOf(hospital)), uint8(PatientRegistry.Role.Facility));
        assertTrue(reg.isProvider(hospital));
    }

    function test_registerProvider_onlyAdmin() public {
        vm.prank(stranger);
        vm.expectRevert("not admin");
        reg.registerProvider(stranger, PatientRegistry.Role.Clinician);
    }

    function test_registerProvider_rejectsBadRoles() public {
        address x = makeAddr("x");
        vm.expectRevert("bad role");
        reg.registerProvider(x, PatientRegistry.Role.Patient);
        vm.expectRevert("bad role");
        reg.registerProvider(x, PatientRegistry.Role.None);
    }

    function test_registerProvider_rejectsZeroAddress() public {
        vm.expectRevert("zero address");
        reg.registerProvider(address(0), PatientRegistry.Role.Clinician);
    }

    function test_registerProvider_cannotOverwriteExistingRole() public {
        vm.expectRevert("already registered");
        reg.registerProvider(alice, PatientRegistry.Role.Clinician); // alice is a patient
        vm.expectRevert("already registered");
        reg.registerProvider(doc, PatientRegistry.Role.Facility);    // doc already a provider
    }

    function test_removeProvider_clearsRoleAndEmits() public {
        vm.expectEmit(true, false, false, false);
        emit PatientRegistry.ProviderRemoved(doc);
        reg.removeProvider(doc);
        assertFalse(reg.isProvider(doc));
        assertEq(uint8(reg.roleOf(doc)), uint8(PatientRegistry.Role.None));
    }

    function test_removeProvider_onlyAdminAndOnlyProviders() public {
        vm.prank(stranger);
        vm.expectRevert("not admin");
        reg.removeProvider(doc);

        vm.expectRevert("not a provider");
        reg.removeProvider(alice);
    }

    function test_transferAdmin() public {
        address n = makeAddr("n");
        reg.transferAdmin(alice);
        assertEq(reg.admin(), alice);

        vm.expectRevert("not admin"); // old admin (this) is locked out
        reg.registerProvider(n, PatientRegistry.Role.Clinician);

        vm.prank(alice);
        reg.registerProvider(n, PatientRegistry.Role.Clinician);
    }

    function test_transferAdmin_guards() public {
        vm.prank(stranger);
        vm.expectRevert("not admin");
        reg.transferAdmin(stranger);

        vm.expectRevert("zero address");
        reg.transferAdmin(address(0));
    }

    function testFuzz_registerPatient(address who, bytes32 id) public {
        vm.assume(uint160(who) > 0xFF && id != bytes32(0));
        vm.assume(reg.roleOf(who) == PatientRegistry.Role.None);
        vm.assume(!reg.pseudoIdTaken(id));
        vm.prank(who);
        reg.registerPatient(id);
        assertTrue(reg.isPatient(who));
        assertEq(reg.pseudoIdOf(who), id);
    }
}
