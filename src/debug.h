#pragma once

#include "controller.h"
#include <string>

std::string FaultTypeToString(Device::FaultType type);
std::string NetworkFaultToString(NetworkInterface::NetworkFaultType type);