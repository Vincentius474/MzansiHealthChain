// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import {PatientRegistry} from "../src/PatientRegistry.sol";

/// Demo data for a freshly deployed chain.
/// Env: DEPLOYER_PRIVATE_KEY (registry admin), PATIENT_PRIVATE_KEY, CLINICIAN_ADDRESS
/// Registers the clinician and patient. Access must be requested and approved by the patient.
contract Seed is Script {
    function run() external {
        string memory json =
            vm.readFile(string.concat("./deployments/", vm.toString(block.chainid), ".json"));
        PatientRegistry reg = PatientRegistry(vm.parseJsonAddress(json, ".PatientRegistry"));
        address clinician = vm.envAddress("CLINICIAN_ADDRESS");

        vm.startBroadcast(vm.envUint("DEPLOYER_PRIVATE_KEY"));
        reg.registerProvider(clinician, PatientRegistry.Role.Clinician);
        vm.stopBroadcast();

        vm.startBroadcast(vm.envUint("PATIENT_PRIVATE_KEY"));
        reg.registerPatient(keccak256("demo-patient-salted-id"));
        vm.stopBroadcast();

        console.log("Seeded: clinician", clinician);
    }
}
