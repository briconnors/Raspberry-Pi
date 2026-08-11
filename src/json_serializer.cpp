
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
        battery.timestamp = data["timestamp"];
        battery.device = data["device"];

        // handle null values during JSON parse
        auto action=data.value("action",json::object());
        battery.last_request=action.value("request","");
        if(action["target"].is_string())
            battery.last_target=action["target"].get<std::string>();
        else
            battery.last_target="";
        if(action["value"].is_number())
            battery.last_value=action["value"].get<int>();
        else
            battery.last_value=0;
        if(action["status"].is_boolean())
            battery.last_status=action["status"].get<bool>();
        else
            battery.last_status=false;
        battery.last_state=action.value("state","");

        battery.soc= data["telemetry"]["home_telemetry"]["soc"];
        battery.voltage = data["telemetry"]["home_telemetry"]["voltage"];
        battery.current = data["telemetry"]["home_telemetry"]["current"];
        battery.pv_watts = data["telemetry"]["home_telemetry"]["pv_watts"];       
        battery.grid_watts = data["telemetry"]["home_telemetry"]["grid_watts"];
        battery.ac_watts = data["telemetry"]["home_telemetry"]["ac_watts"];
        battery.dc_watts = data["telemetry"]["home_telemetry"]["dc_watts"];
        
        battery.grid_permission = data["telemetry"]["grid_permission"]["value"];

        battery.ac_output= data["telemetry"]["ac_output"]["value"];
        battery.dc_output= data["telemetry"]["dc_output"]["value"];
        battery.ac_input= data["telemetry"]["ac_input"]["value"];
        battery.dc_input= data["telemetry"]["dc_input"]["value"];
        battery.ac_input_setting= data["telemetry"]["ac_input_setting"]["value"];
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
    payload["request"] = command.request;
    payload["target"] = command.target;
    payload["value"] = command.value;

    //convert the JSON object into a string
    return payload.dump();
}

std::string BuildBatteryScheduleJson(
    const BatterySchedule& schedule){
    json payload;

    payload["device"] = "bluetti_ac200";
    payload["timestamp"] = std::chrono::duration_cast<std::chrono::seconds>(std::chrono::system_clock::now().time_since_epoch()).count();
    payload["request"] = schedule.request;

    payload["charge_start"] = schedule.charge_start;
    payload["charge_end"] = schedule.charge_end;

    payload["discharge_start"] = schedule.discharge_start;
    payload["discharge_end"] = schedule.discharge_end;

    return payload.dump();
}