//Summary of config.h: all constant/scalable values for mqtt setup with a plug are defined, 
//along with constant constraints of the battery

#pragma once //no reinitializing
#include <string> //human readable text

// mqtt broker pi settings
const std::string MQTT_BROKER = "10.42.0.1"; //192.168.1.50 for different machine acting as controller
const int MQTT_PORT = 1883; //8883=encrypted MQTT (TLS) standard=1883
const std::string MQTT_USER="brianna";
const std::string MQTT_PASS="";

// shared location for now
const std::string LOCATION = "";

// tasmota test topics (smart plug client for now)
const std::string PLUG_NAME = std::string("plug"); //MQTT topic name (WiFiManager identifier chosen)
const std::string TOPIC_CMD_POWER = std::string("cmnd/") + LOCATION + PLUG_NAME + "/POWER";
const std::string TOPIC_STAT_POWER = std::string("stat/") + LOCATION + PLUG_NAME + "/POWER";
const std::string TOPIC_TELE_STATE = std::string("tele/") + LOCATION + PLUG_NAME + "/STATE";

// battery test topics
const std::string BATTERY_NAME = "battery";
const std::string TOPIC_COMMAND = std::string("cmnd/") + LOCATION + BATTERY_NAME + "/CONTROL";
const std::string TOPIC_STATUS = std::string("stat/") + LOCATION + BATTERY_NAME + "/STATUS";
const std::string TOPIC_TELEMETRY = std::string("tele/") + LOCATION + BATTERY_NAME + "/STATE";
const std::string TOPIC_SCHEDULE = std::string("schedule/") + LOCATION + BATTERY_NAME + "/STATE";

// battery scalable limitations
const double MIN_SOC = 20.0;// minimum percent (%) of battery allowed
const double MAX_SOC = 100.0;// maximum percent (%) of battery allowed
const double MAX_SOC_JUMP = 10.0; // catch for strange data

const double MAX_CURRENT = 10.0;// maximum current (Amps) allowed through the plug/battery
const double MAX_CURRENT_JUMP = 5.0;

const double MIN_VOLTAGE = 0.0; // minimum voltage (Volts)
const double MAX_VOLTAGE = 12.0; // maximum voltage (Volts)
const double MAX_VOLTAGE_JUMP = 5.0;

const double LOAD_TOLERANCE = 10.0;
const double STALE_TIMEOUT = 10.0;// time limit (secs) for flagging stale readings 