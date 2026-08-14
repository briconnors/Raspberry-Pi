#include "config.h"//saved constants to reference (broker ip, topics, limits, device name)
#include "devices.h"
#include "controller.h"
#include "json_serializer.h"
#include <string>
#include <iostream>
#include <cmath>

//MAIN FUNCTIONS------------------------------------
void Controller::SetGridOffsetDemand(double demand){
    gridOffsetDemand = demand;
}
//start function to pair MQTT broker with clients:
void Controller:: Initialize(){
    //connect controller to the broker (Mosquitto)
    if (!ConnectMqtt()){
        std::cerr << "MQTT initialization failed.\n"<< std::endl;
    }
    //subscribe to broker topics
    SubscribeTopic(TOPIC_TELEMETRY);
}

//main run loop controlling function to monitor/influence system
void Controller::Run(){
    MonitorNetwork();
    UpdateState();
    VerifyCommand();
    EvaluateHealth(device);
    GenerateCommand();
    SendCommand();
    // after entire loop, update the storage of the last set of telemetry
    if(HasTelemetry()){
        lastBatteryData=battery;
        validLastBatteryData=true;
    }
}

void Controller::MonitorNetwork(){
    ProcessMessages(); // wait for incoming messages from the broker and parse the JSON
}

void Controller::UpdateState(){
    GetLatestBattery(battery); // update data structure with the latest battery information
    PrintState();
}

void Controller::EvaluateHealth(Device& device){
    // reset states to healthy unless a check fails each loop
    device.fault = Device::FaultType::none; 
    device.constraint = Device::ConstraintType::none;
    device.canCharge = true;
    device.canDischarge = true;
    // FAULTS (indicate an issue in the program)
    // no valid telemetry has been received yet
    if(!HasTelemetry()){
        device.fault=Device::FaultType::communicationError;
        device.canCharge=false;
        device.canDischarge=false;
        SetState(State::fault);
        return;
    }
    // check how long it has been since valid telemetry was received
    if(GetTelemetryAge()>STALE_TIMEOUT){
        device.fault=Device::FaultType::staleTelemetry;
        device.canCharge=false;
        device.canDischarge=false;
        SetState(State::fault);
        return;
    }
    // check for jumps in the battery data that are outside of the expected range
    if (validLastBatteryData && std::abs(battery.soc - lastBatteryData.soc) > MAX_SOC_JUMP){
        device.fault = Device::FaultType::invalidSOC;
        SetState(State::fault);
    }
    else if (validLastBatteryData && std::abs(battery.current - lastBatteryData.current) > MAX_CURRENT_JUMP){
        device.fault = Device::FaultType::invalidCurrent;
        SetState(State::fault);
    }
    else if (validLastBatteryData && std::abs(battery.voltage - lastBatteryData.voltage) > MAX_VOLTAGE_JUMP){
        device.fault = Device::FaultType::invalidVoltage;
        SetState(State::fault);
    }
    // check for values against the expected ranges
    else if (battery.soc < 0.0 || battery.soc > 100.0){
        device.fault = Device::FaultType::invalidSOC;
        SetState(State::fault);
    }
    else if (std::abs(battery.current) > MAX_CURRENT){
        device.fault = Device::FaultType::invalidCurrent;
        SetState(State::fault);
    }
    else if (battery.voltage < MIN_VOLTAGE || battery.voltage > MAX_VOLTAGE){
        device.fault = Device::FaultType::invalidVoltage;
        SetState(State::fault);
    }
    // CONSTRAINTS (indicate a limitation on the system's ability to meet the grid-offset demand)
    else if (battery.soc < MIN_SOC){ // hard coded minimum state of charge for battery life
        device.constraint = Device::ConstraintType::lowBattery;
        device.canDischarge = false;
    }
}

void Controller::GenerateCommand(){
    double localLoad = battery.ac_watts+battery.dc_watts;
    bool hasLoad = localLoad>LOAD_TOLERANCE;
    bool gridDemand = gridOffsetDemand>0;
    
    // if there's fault, don't issue any commands to the battery
    if(device.fault != Device::FaultType::none){
        requestedCommand = CommandType::none;
    }
    // ConEd wants grid relief and there's something to power
    else if(gridDemand&&hasLoad&&device.canDischarge){
        requestedCommand=CommandType::startDischarging;
    }
    // ConEd wants grid relief but there's no local demand
    else if(gridDemand&&!hasLoad){
        if(currentCommand==CommandType::startCharging){
            requestedCommand=CommandType::stopCharging;
        }
        else if(currentCommand==CommandType::startDischarging){
            requestedCommand=CommandType::stopDischarging;
        }
        else{
            requestedCommand=CommandType::none;
        }
    }
    // no grid-offset event, return to grid/pass-through and recharge if needed
    else if(!gridDemand&&device.canCharge){
        requestedCommand=CommandType::startCharging;
    }
    // no offset demand and battery doesn't need charging
    else{
        requestedCommand=CommandType::none;
    }
}

void Controller::SendCommand(){
    if(requestedCommand == currentCommand){
        return;
    }
    switch(requestedCommand){
        case CommandType::startCharging:
            SendBatteryCommand("grid_permission",1);
            SendBatteryCommand("ac_input",1);
            SendBatteryCommand("ac_input_setting",1);
            break;
        case CommandType::stopCharging:
            SendBatteryCommand("ac_input_setting",0);
            break;
        case CommandType::startDischarging:
            SendBatteryCommand("ac_output",1);
            break;
        case CommandType::stopDischarging:
            SendBatteryCommand("ac_output",0);
            break;
        case CommandType::none:
            return;
        default:
            return;
    }
}
// helper to prevent huge controller loop 
bool Controller::SendBatteryCommand(const std::string& target,int value){
    BatteryCommand command;
    command.request = "write";
    command.target = target;
    command.value = value;

    std::string payload = BuildBatteryCommandJson(command);

    return PublishMessage(TOPIC_COMMAND,payload);
}

void Controller::VerifyCommand(){
    if(battery.last_request != "write"){
        return;
    }
    if(battery.last_target == "ac_input_setting"){
        if(battery.last_value == battery.ac_input_setting){
            std::cout << "Charging command verified successfully." << std::endl;
            currentCommand = requestedCommand;
            if (requestedCommand == CommandType::startCharging){
                SetState(State::charging);
            }
            else if (requestedCommand == CommandType::stopCharging){
                SetState(State::idle);
            }
        }
        else{
            std::cerr << "Charging command verification failed." << std::endl;
        }
    }
    else if(battery.last_target == "ac_output"){
        if(battery.last_value == battery.ac_output){
            std::cout << "Discharging command verified successfully." << std::endl;
            currentCommand = requestedCommand;
            if (requestedCommand == CommandType::startDischarging){
                SetState(State::discharging);
            }
            else if (requestedCommand == CommandType::stopDischarging){
                SetState(State::idle);
            }
        }
        else{
            std::cerr << "Discharging command verification failed." << std::endl;
        }
    }
}

//STATE FUNCTIONS-------------------------------
void Controller::SetState(State newState){
    currentState = newState;
    //add fault state!
}

void Controller::PlugOn(){
    if(PublishMessage(TOPIC_CMD_POWER, "ON")){
                currentCommand = requestedCommand;
            }
}

void Controller::PlugOff(){
    if(PublishMessage(TOPIC_CMD_POWER, "OFF")){
                currentCommand = requestedCommand;
            }
}
