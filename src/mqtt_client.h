//Summary of mqtt_client.h: declares the helper functions that other files can call, but the actual MQTT logic
//is stored inside of mqtt_client.cpp

#pragma once
#include <string>
#include "devices.h"

bool ConnectMqtt();
bool PublishMessage(const std::string& topic, const std::string& payload);
bool SubscribeTopic(const std::string& topic);
bool GetLatestBattery(DeviceInformation& batteryData);
bool HasTelemetry();
double GetTelemetryAge();
void ProcessMessages();
void DisconnectMqtt();
