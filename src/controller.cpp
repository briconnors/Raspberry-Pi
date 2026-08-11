#include "config.h"//saved constants to reference (broker ip, topics, limits, device name)
#include "devices.h"
#include "controller.h"
#include "json_serializer.h"
#include <string>
#include <iostream>

//MAIN FUNCTIONS------------------------------------
//start function to pair MQTT broker with clients:
void Controller:: Initialize(){
    //connect controller to the broker (Mosquitto)
    if (!ConnectMqtt()){
        std::cerr << "MQTT initialization failed.\n"<< std::endl;
    }
    //subscribe to broker topics
    SubscribeTopic(TOPIC_TELEMETRY);

}
//main controlling function to monitor/influence system
void Controller::Run(){
    MonitorNetwork();
    UpdateState();
    EvaluateHealth(device);
    GenerateCommand();
    SendCommand();
    VerifyCommand();
}

void Controller::MonitorNetwork(){
    ProcessMessages();
}

void Controller::UpdateState(){
    GetLatestBattery(battery);
    PrintState();
}

void Controller::EvaluateHealth(Device& device){
    if (battery.soc < MIN_SOC){ // hard coded minimum state of charge for battery life
        device.fault = Device::FaultType::lowBattery;
        SetState(State::fault);
    }
    
    
    else if (battery.soc >= MIN_SOC ){
        device.fault = Device::FaultType::none;
    }
}

void Controller::GenerateCommand(){
    // temporary for testing!!
    requestedCommand = CommandType::startCharging;
    // for thresholds later:
    // if(device.SOC < MIN_SOC)
    //     requestedCommand = CommandType::startCharging;
    // else if(device.SOC > MAX_SOC)
    //     requestedCommand = CommandType::stopCharging;
}
//translate the requested command into MQTT text:
void Controller::SendCommand(){
    // already in desired state
    if(requestedCommand == currentCommand){
        return;
    }
    //temporary command object that will later be converted to JSON
    BatteryCommand command;
    switch(requestedCommand){
        case CommandType::startCharging:
            command.request = "write";
            command.target = "ac_input_setting";
            command.value = 1;
            break;
        case CommandType::stopCharging:
            command.request = "write";
            command.target = "ac_input_setting";
            command.value = 0;
            break;
        default:
            break;
    }
    std::string payload = BuildBatteryCommandJson(command);

    PublishMessage(
        TOPIC_COMMAND,
        payload);

    currentCommand = requestedCommand; //update command variable
}

void Controller::VerifyCommand(){

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
