//devices.h Summary: defines the data structure for a device, which includes 
//all relevant info about the system, such as identification, battery state, timestamps, and status flags.

#pragma once //prevents multiple inclusions of this header file
#include <string>//allow string references

//define a custom data type called DeviceInformation to store all information about one plug/battery system
struct DeviceInformation{//custom data type called a device to store all information about one plug/battery system
    //identifications to set up fleet controls
    std::string id;
    std::string room;
    std::string floor;
    std::string building;
    std::string block;
    std::string neighborhood;
    std::string borough;
    std::string mqttBaseTopic;
    //current battery state behavior
    double soc = 0.0;//state of charce (%)
    double voltage = 0.0;
    double current = 0.0;
    double pv_watts = 0.0;
    double grid_watts = 0.0;
    double ac_watts = 0.0;
    double dc_watts = 0.0;
    bool grid_permission = false; //permission to draw from the grid
    
    double timestamp = 0.0; // time stamp to/from battery message
    std::string device;
    double ac_output = 0.0;
    double dc_output = 0.0;
    double ac_input = 0.0;
    double dc_input = 0.0;
    double ac_input_setting = 0.0;

    std::string last_request;
    std::string last_target;
    int last_value = 0;
    bool last_status = false;
    std::string last_state;

    double switchPower = 0.0;//current plug power reading
    double switchCurrent = 0.0;//current plug current reading
    //timestamps for each state
    double lastTimeUpdate = 0.0;
    double lastPowerUpdate = 0.0; 
    double lastSocUpdate = 0.0;
    //status flags if the system is ready to be used, or currently communicating and reachable
    bool batteryAvailable = false; 
    bool batteryOnline = false; 
    bool brokerOnline = false;
};

//battery command desired states
struct BatteryCommand
{
    std::string request;
    std::string target;
    int value;
};

struct BatterySchedule
{
    std::string request;
    std::string charge_start;
    std::string charge_end;
    std::string discharge_start;
    std::string discharge_end;
};