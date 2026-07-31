
#include "json_serializer.h"
#include <iostream>
#include <chrono>
#include <nlohmann/json.hpp> //JSON parsing library
using json = nlohmann::json;

bool ParseBatteryTelemetry(const std::string& payload,DeviceInformation& battery){
    try{
        //convert the MQTT payload string into a JSON object
        json data=json::parse(payload);
        //copy telemetry values from the JSON packet into the battery structure
        battery.timestamp=
            data["timestamp"];
        battery.device = // note future: move to another function for only device info for expansion
            data["device"];
        battery.soc=
            data["telemetry"]["home_telemetry"]["soc"];
        battery.voltage =
            data["telemetry"]["home_telemetry"]["voltage"];
        battery.current =
            data["telemetry"]["home_telemetry"]["current"];
        battery.pv_watts =
            data["telemetry"]["home_telemetry"]["pv_watts"];       
        battery.ac_output=
            data["telemetry"]["ac_output"]["value"];
        battery.dc_output=
            data["telemetry"]["dc_output"]["value"];
        battery.ac_input=
            data["telemetry"]["ac_input"]["value"];
        battery.dc_input=
            data["telemetry"]["dc_input"]["value"];
        battery.ac_input_setting=
            data["telemetry"]["ac_input_setting"]["value"];
        return true;
    }
    catch(const json::exception& e){
        std::cerr<<"JSON parse failed: "<<e.what()<<std::endl;
        return false;
    }
}

std::string BuildBatteryCommandJson(const BatteryCommand& command){
    json payload; // create an empty JSON object

    payload["device"] = "bluetti_ac200"; // device information
    payload["timestamp"] = std::chrono::duration_cast<std::chrono::seconds>(std::chrono::system_clock::now().time_since_epoch()).count(); // time the command was created

    //controller commands
    payload["request"] = "write";
    payload["target"] = "ac_output";
    payload["value"] = command.ac_output;

    //convert the JSON object into a string
    return payload.dump();
}