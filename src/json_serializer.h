#pragma once

#include <string>
#include "devices.h"

//parse incoming JSON from BLE coms py actuator
bool ParseBatteryTelemetry(
    const std::string& payload,
    DeviceInformation& battery
);

//build a JSON string from a controller command
std::string BuildBatteryCommandJson(
    const BatteryCommand& command);