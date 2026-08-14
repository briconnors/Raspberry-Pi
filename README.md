# **Battery Controller**
By Brianna Connors (Jan 2026-Aug 2026)

C++ prototype to monitor the fleet of grid-offset batteries, receive/send telemetry and commands between IoT components across MQTT, and collect data for future ML analysis. JSON is utilized to standardize data exchange between programs and devices. 

CMake was used as the build system generator, creating a compiled C++ executable that can be ran directly from the file explorer during development or uploaded to the hardware. After pairing the computer or device to the broker network, the battery actuator and telemetry BLE link Python script can be initialized from the terminal.

The referenced loop.py BLE link Python script is currently configured with the EL400 model, and the AC200 model addition is under development to create a miniature fleet simulating a grid-offset demand response.
___
## System Architecture
The total system consists of the battery/solar panel, local BLE actuator, controller, and data dashboard, each connected through a central broker to establish the MQTT communication layer.

![System Architecture](docs/system_prototype.png)
*Figure 1. System architecture and communication flow.*
___
## Controller Structure
In the following section, the purpose and trajectory of each file of the source directory is detailed, along with each functions' role. 

### config.h
> Contains all static inputs for pairing the controller as a client to the broker, parameterized topics (commands, status, telemetry, scheduling) for expanding the system from one battery to a fleet, and static constraints/thresholds for a given battery model.
___
### controller.cpp
> The primary file being referenced in the main loop, containing all decision logic (monitor network -> update state -> print state -> evaluate health -> generate command -> send command -> verify command -> update battery data storage)

**Initialize**: code ran once at the beginning, initializes the MQTT client, pairs to broker, and subscribes to the payload topics.

**MonitorNetwork**: processes incoming MQTT traffic from the broker using the main JSON serializer to parse the payload into useable data

**UpdateState**: stores newest battery telemetry packet and prints the current controller state to the terminal for debugging

**EvaluateHealth**: checks telemetry against static battery limits and the previous telemetry packet to identify invalid SOC, current, voltage, or stale data, then determines whether the battery is available to charge/discharge

**GenerateCommand**: uses grid-offset demand, local AC/DC load, battery health, and charge/discharge availability to determine the next controller command

**SendCommand**: converts the requested controller action into the required battery control sequence, builds each command into JSON, and publishes it to the actuator through MQTT

**SendBatteryCommand**: helper function used by SendCommand to build and publish individual battery write commands without repeating logic

**VerifyCommand**: compares the actuator-reported write request and returned device state against the requested command to confirm a successful charge/discharge and report command failures

**SetState**: updates the data structure to reflect resulting system state for future analysis/feedback verification
___
### controller.h
> Organizes the classes, bools, and member functions used for network communication, telemetry, state monitoring, and fault recognition.

**NetworkInterface**: MQTT bools and member functions for configuration of client/broker connection and classes for states (disconnected,connecting,connected,subscribed) and faults (stale, dropped, and garbage data, none)

**Device**: stores device health and availability, separating faults (invalid SOC, voltage, current, communication) from operating constraints (low battery and fleet-spacing limitations), along with canCharge/canDischarge flags

**Controller**: member classes for the primary logic (initialize, run, monitor network, update state, print state, evaluate health, generate command, send command, verify command, update battery data storage) states (idle, charging, discharging, fault) and command states (none, start charging, start discharging, stop charging, stop discharging) 

**LastBatteryData**: battery storage of the previous telemetry packet for comparison during health evaluation to identify unreasonable telemetry jumps
___
### debug.cpp
> Contains all prints helpful for debugging (fault types for network and device levels and prints for the system state)
**FaultTypeToString**: converts stored device fault enums into readable strings 

**NetworkFaultToString**: converts stored network fault enums into readable strings

**PrintNetworkConditions**: prints the current MQTT/network status flags to the terminal

**PrintState**: prints the current controller state and newest battery telemetry to the terminal
___
### debug.h
> Contains function declarations used in debug.cpp, establishing the return type and parameters.
___
### devices.h
> Establishes structures for the storage of a single device's telemetry, commands, and schedule during reading and writing.

**DeviceInformation**: stores the newest parsed battery telemetry, switch/input states, actuator response information, timestamp, and device identifier

**BatteryCommand**: stores an individual battery write request, including request type, target, and value

**BatterySchedule**: stores the values/actions needed to construct a battery scheduling request
___
### json_serializer.cpp
> Includes functions utilized in handling JSON messages based on nlohmann's library (parsing telemetry and building battery commands/schedule)
> 
**ParseBatteryTelemetry**: parses incoming telemetry JSON into the DeviceInformation structure used by the controller

**BuildBatteryCommandJson**: converts a BatteryCommand structure into the JSON payload for immediate individual or hard-coded commands

**BuildBatteryScheduleJson**: converts battery scheduling information into the JSON payload used for scheduling
___
### json_serializer.h
> Includes function declarations used in json_serializer.cpp (telemetry, command, and scheduling), establishing the return type and parameters defined in devices.h.
___
### main.cpp
> Referencing controller.cpp, the main loop references the initialize function once on startup to establish the MQTT connection. Then the primary run loop is referenced to call the controller state machine (run, monitor network, update state, print state, evaluate health, generate command, send command, verify command, update battery data storage)
___
### mqtt_client.cpp
> Contains all necessary logic using Mosquitto (libmosquitto) to establish a connection to a broker, subscribe to each topic defined in config.h, receive each topics payload, parse the message through json_serializer.cpp and store the data, publish commands from the controller to the battery, and disconnect from the broker cleanly.

**ConnectMqtt**: initializes the Mosquitto client, registers the callback so incoming subscribed messages are automatically processed, inputs the network information (username/password) declared in config.h, and opens the MQTT port to connect the client to the broker.

**SubscribeTopic**: subscribes the connected MQTT client to a specified broker topic

**ProcessMessages**: processes pending MQTT network traffic so subscribed messages can be received and callbacks executed

**OnMessage**: receives subscribed MQTT messages, converts the payload into a string, parses battery telemetry through json_serializer.cpp, and stores the newest successfully parsed battery data

**GetLatestBattery**: copies the newest successfully parsed battery telemetry into the controller's battery data structure for use in the current control loop

**PublishMessage**: check the connection, then publish the topic and payload to the network over MQTT, and hold the Mosquitto connection open and process network traffic such as reading incoming packets, sending outgoing packets, managing pings, and reconnections.

**DisconnectMqtt**: remove the Mosquitto client, free all memory and resources, reset the client pointer to null and prevent memory leaks to fully and cleanly remove the client.
___
### mqtt_client.h
> Establishes the function declarations for mqtt_client.cpp including connecting, publishing, subscribing, updating storage, processing messages, and disconnecting.
___
## Future Work
- Finish adding more devices to simulate a fleet (config.h)
- Add logic to utilize the fault recognition from the Python BLE coms actuator level (EvaluateHealth, controller.cpp)
- Add fleet-oriented characterization of individual unit health to report total SOC available across all batteries (EvaluateHealth, controller.cpp)
- Add logic creating an alert or other notification of faults and more cases (controller.cpp)
- Add logic to calculate schedule needed based on input load and current fleet health
- Add main ML command pipeline (if there’s a grid-offset_demand (main trigger) and the battery is healthy -> report the amount of charge available -> trigger schedule)
- Add verification logic for multi-step scheduling sequences (verifyCommand, controller.cpp)
- Remove debug entirely in the future to prevent constant additional feedback in the main controller .exe terminal (simple debug prints)
- Replace the static demand input with Con-ed or ML model demand information as the input for scheduling actuation (main.cpp)
- Replace loop counter with an infinite while true loop (development counter to allow easy debugging/troubleshooting) (main.cpp)


  




