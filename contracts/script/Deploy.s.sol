// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import {PatientRegistry} from "../src/PatientRegistry.sol";
import {ConsentManagement} from "../src/ConsentManagement.sol";
import {AccessControl} from "../src/AccessControl.sol";
import {AuditLog} from "../src/AuditLog.sol";

/// Env: DEPLOYER_PRIVATE_KEY, RELAYER_ADDRESS
/// Writes addresses to deployments/<chainId>.json (used by scripts/sync_env.py).
contract Deploy is Script {
    function run() external {
        address relayer = vm.envAddress("RELAYER_ADDRESS");

        vm.startBroadcast(vm.envUint("DEPLOYER_PRIVATE_KEY"));
        PatientRegistry reg = new PatientRegistry();
        ConsentManagement con = new ConsentManagement(reg);
        AccessControl acl = new AccessControl(reg, con);
        AuditLog audit = new AuditLog();
        audit.setLogger(relayer, true);
        vm.stopBroadcast();

        console.log("PatientRegistry   ", address(reg));
        console.log("ConsentManagement ", address(con));
        console.log("AccessControl     ", address(acl));
        console.log("AuditLog          ", address(audit));

        string memory k = "deployment";
        vm.serializeAddress(k, "PatientRegistry", address(reg));
        vm.serializeAddress(k, "ConsentManagement", address(con));
        vm.serializeAddress(k, "AccessControl", address(acl));
        string memory json = vm.serializeAddress(k, "AuditLog", address(audit));
        vm.writeJson(json, string.concat("./deployments/", vm.toString(block.chainid), ".json"));
    }
}
