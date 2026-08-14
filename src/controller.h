// controller.h Summary: establish the controller class and its methods
#pragma once
#include "mqtt_client.h"
#include "devices.h"
#include <string>

// networking conditions of the state machine
class NetworkInterface
{
    // initialize state bools to false, will be set to true when the state is reached
public:
    bool networkReady = false;
    bool brokerAvailable = false;
    bool mqttInitialized = false;
    bool packetReceived = false;
    bool messageProcessed = false;
    bool commandEnabled = false;
    bool packetSent = false;

    // establish controls for the network layer
    bool Initialize();
    bool Connect();
    bool Disconnect();
    bool Subscribe();
    bool Publish();

    // define the possible states of the network layer
    enum class NetworkState
    {
        disconnected, // not connected to the broker
        connecting,   // attempting to connect to the broker
        connected,    // connected to the broker and ready to send/receive messages
        subscribed    // subscribed to the topics and ready to receive messages
    };

    // define possible faults of the network layer
    enum class NetworkFaultType
    {
        staleData,   // data not updated in time
        droppedData, // no message recieved during handshake
        garbageData, // data recieved but not valid
        none
    };
    void PrintNetworkConditions();

private:
    NetworkState networkState = NetworkState::disconnected; // initialize as disconnected
    NetworkFaultType networkFault = NetworkFaultType::none; // initialize as no fault
};

// main system state machine class conditions
class Device
{
public:
    // defines the possible faults responsible to failure
    enum class FaultType
    {
        none,       // no fault
        invalidSOC, // invalid data out of range (value or jump)
        invalidVoltage,
        invalidCurrent,
        communicationError,
        staleTelemetry,
    };
    enum class ConstraintType
    {
        none,       // no issues
        lowBattery, // battery is below minimum SOC recommendation
        tooClose,   // battery is located near another battery in the same schedule batch
    };
    // private:
    FaultType fault = FaultType::none;
    ConstraintType constraint = ConstraintType::none;

    bool telemetryValid = false;
    bool available = false;
    bool canCharge = false;
    bool canDischarge = false;
};

class Controller
{
public:
    // establish the controller states
    void SetGridOffsetDemand(double demand);
    void Initialize();
    void Run();
    void MonitorNetwork();
    void UpdateState();
    void PrintState(); // display the current battery state in terminal
    void EvaluateHealth(Device &device);
    void GenerateCommand();
    void SendCommand();
    bool SendBatteryCommand(const std::string &target, int value);
    void VerifyCommand();
    void UpdateBattery(const DeviceInformation &newData);
    void PlugOn();
    void PlugOff();

    enum class State
    {
        idle,        // system waiting for discharge
        charging,    // system currently charging
        discharging, // system currently discharging
        fault,       // system has a fault and is not operating
    };

    enum class CommandType
    {
        none,             // no command issued
        startCharging,    // command to start charging
        startDischarging, // command to start discharging
        stopCharging,     // command to stop charging
        stopDischarging,  // command to stop discharging
    };
    void SetState(State newState);

private:
    // establish ownership of the other system objects:
    NetworkInterface networkInterface;
    Device device;
    DeviceInformation battery;
    DeviceInformation lastBatteryData;

    bool validLastBatteryData = false; // flag to indicate if lastBatteryData has been initialized
    double gridOffsetDemand = 0.0;

    State currentState = State::idle;               // initialize as idle state
    CommandType currentCommand = CommandType::none; // initialize as no command issued
    CommandType requestedCommand = CommandType::none;
};
