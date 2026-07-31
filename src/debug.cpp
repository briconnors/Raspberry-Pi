// debugging faults and prints:
#include "debug.h"
#include "devices.h"
#include "controller.h"

#include <iostream>
#include <string>

//defining the failure modes in readable text:
std::string FaultTypeToString(Device::FaultType type){
    switch(type){
        case Device::FaultType::none:
            return "no_fault";
        case Device::FaultType::lowBattery:
            return "low_battery";
        case Device::FaultType::tooClose:
            return "too_close";
        case Device::FaultType::invalidSOC:
            return "invalid_soc";
        case Device::FaultType::invalidVoltage:
            return "invalid_voltage";
        case Device::FaultType::invalidCurrent:
            return "invalid_current";
        default:
            return "unknown_fault";
    }
}
std::string NetworkFaultToString(NetworkInterface::NetworkFaultType type){
    switch(type){
        case NetworkInterface::NetworkFaultType::none:
            return "no_fault";
        case NetworkInterface::NetworkFaultType::staleData:
            return "stale_data";
        case NetworkInterface::NetworkFaultType::droppedData:
            return "dropped_data";
        case NetworkInterface::NetworkFaultType::garbageData:
            return "garbage_data";
        default:
            return "unknown_fault";
    }
}

//debugging prints and framework for checking network functionalty:
void NetworkInterface::PrintNetworkConditions(){
    if (brokerAvailable){
        std::cout << "Broker is available." << std::endl;
    }
    if (mqttInitialized){
        std::cout << "MQTT is initialized." << std::endl;
    }
    if (packetReceived){
        std::cout << "Incoming packet has been received." << std::endl;
    }
    if (messageProcessed){
        std::cout << "Message has been processed." << std::endl;
    }
    if (commandEnabled){
        std::cout << "Command is enabled." << std::endl;
    }
    if (packetSent){
        std::cout << "Outgoing packet has been sent." << std::endl;
    }
}

void Controller::PrintState(){
    switch(currentState){
    case State::idle:
        std::cout << "System is idle" << std::endl;
        break;
    case State::charging:
        std::cout << "System is charging" << std::endl;
        break;
    case State::discharging:
        std::cout << "System is discharging" << std::endl;
        break;
    case State::fault:
        std::cout << "System has a fault" << std::endl;
        break;
    }
}