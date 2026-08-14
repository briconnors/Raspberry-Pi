//Summary of mqtt_client.cpp: establishes MQTT connection to the pi broker,
//publishing a message, then disconnecting after running once successfully

#include "mqtt_client.h" //declares helper functions for this file
#include "config.h" //declares constants
#include "devices.h"
#include "json_serializer.h"
#include <mosquitto.h> //mosquitto C library API to establish
#include <iostream> //allows printing to terminal with std::cer
#include <chrono> //allows time tracking for stale telemetry

static mosquitto* client=nullptr; //makes a client pointer to hold MQTT object
                                  //constant, pointer to mosquitto type client, initially null
static DeviceInformation latestBattery; // temporary storage for the newest telemetry received
static bool hasTelemetry = false; // flag to indicate valid telemetry
static std::chrono::steady_clock::time_point lastTelemetryTime; // timestamp of the last telemetry received

//callback function automatically called whenever a subscribed MQTT message arrives
static void OnMessage(
    mosquitto*,
    void*,
    const mosquitto_message* msg){
    //display received topic for debugging
    std::cout<<"Topic: "<<msg->topic<<std::endl;
    //display received payload for debugging
    std::cout<<"Payload: "
             <<std::string(static_cast<char*>(msg->payload),msg->payloadlen)
             <<std::endl;
    //assemble payload into a C++ string so it can be passed to the JSON parser
    std::string payload(
        static_cast<char*>(msg->payload),
        msg->payloadlen
    );
    //temporary storage for newly parsed battery data
    DeviceInformation battery;
    //attempt to parse the JSON payload into the battery structure
    if(ParseBatteryTelemetry(payload,battery)){
        //replace the previous battery information with the newest telemetry
        latestBattery = battery;
        lastTelemetryTime = std::chrono::steady_clock::now();
        hasTelemetry = true;
        std::cout<<"Telemetry updated successfully."<<std::endl;
    }
    else{
        std::cerr<<"Failed to parse battery telemetry."<<std::endl;
    }

    //later:
    //set packetReceived=true
}
//helper bools to return the latest battery telemetry to the controller
bool GetLatestBattery(DeviceInformation& batteryData){
    batteryData = latestBattery;
    return true;
}
bool HasTelemetry(){
    return hasTelemetry;
}
double GetTelemetryAge(){
    if(!hasTelemetry){
        return 0.0;
    }
    auto now=std::chrono::steady_clock::now();
    return std::chrono::duration<double>(now-lastTelemetryTime).count();
}

//main initialization call to setup MQTT client to broker connection
bool ConnectMqtt(){//defining function to return a true/false
    //prevent calling multiple times
    if(client){
        return true;
    }
    
    mosquitto_lib_init();//initializes the mosquitto library
    client=mosquitto_new(nullptr,true,nullptr);//creates and stores MQTT client 
                                               //(no custom ID, clean session,no custom pointer attached)
    if(!client){//if the MQTT client doesn't exist
        std::cerr<<"Failed to create MQTT client."<<std::endl;//print error notification
        return false;//exits the function, sends back false to main.cpp
    }
    //register callback so incoming subscribed messages are automatically processed
    mosquitto_message_callback_set(client,OnMessage);
    //note:rc stands for return code, the integer returned by each function stored temporarily in an integer
    int rc=mosquitto_username_pw_set(client,MQTT_USER.c_str(),MQTT_PASS.c_str());//call function from mosquitto
                //library to enter plug user and password, then store result (target object, convert strings to C)
    //password initialization:
    if(rc!=MOSQ_ERR_SUCCESS){//check if return code is equal to the success target, if it's not:
        std::cerr<<"Failed to set MQTT username/password."<<std::endl;//print error notification
        mosquitto_destroy(client);//destroy failed client object
        client=nullptr;//reset the pointer since the client doesn't exist
        mosquitto_lib_cleanup();
        return false;//end the function, sends false back to main.cpp
    }
    //broker connection attempt:
    rc=mosquitto_connect(client,MQTT_BROKER.c_str(),MQTT_PORT,60);//call mosquitto function to open MQTT connection
                                                        //(target client, broker definition, port, keepalive time [sec])
    if(rc!=MOSQ_ERR_SUCCESS){//check if return code is equal to the success target, if it's not:
        std::cerr<<"Failed to connect to broker: "<<mosquitto_strerror(rc)<<std::endl;//print error notification
                                                                    //with readable output of failure cause
        mosquitto_destroy(client);//destroy failed client object
        client=nullptr;//reset the pointer since the client doesn't exist
        mosquitto_lib_cleanup();
        return false;//end the function, sends false back to main.cpp
    }
    std::cout << "Connected to MQTT broker." << std::endl;
    return true;//if the connection succeeds (auth setup and pair successful) then the function returns true to main
}

//subscribe controller to a MQTT topic so incoming messages can be received
bool SubscribeTopic(const std::string& topic){
    //verify MQTT client exists before subscribing
    if(!client){
        std::cerr<<"MQTT client is not connected, subscribe topic failed."<<std::endl;
        return false;
    }
    //attempt to subscribe to requested topic
    int rc=mosquitto_subscribe(
        client,
        nullptr,
        topic.c_str(),
        1
    );
    //report subscription errors
    if(rc!=MOSQ_ERR_SUCCESS){
        std::cerr<<"Failed to subscribe: "<<mosquitto_strerror(rc)<<std::endl;
        return false;
    }
    std::cout<<"Subscribed to "<<topic<<std::endl;
    return true;
}

void ProcessMessages(){
    if(client){
        mosquitto_loop(client,0,1);
    }
}

//publish command to the client from the controller
bool PublishMessage(const std::string& topic,const std::string& payload){
    if(!client){
        std::cerr<<"MQTT client is not connected, publish message failed."<<std::endl;
        return false;
    }
    int rc=mosquitto_publish(
        client,
        nullptr,
        topic.c_str(),
        static_cast<int>(payload.size()),
        payload.c_str(),
        1,
        false
    );
    if(rc!=MOSQ_ERR_SUCCESS){
        std::cerr<<"Failed to publish message: "<<mosquitto_strerror(rc)<<std::endl;
        return false;
    }
    mosquitto_loop(client,1000,1);
    return true;
}

//data cleaning disconnect from MQTT
void DisconnectMqtt(){
    if(client){
        mosquitto_disconnect(client);
        mosquitto_destroy(client);
        client=nullptr;
    }
    mosquitto_lib_cleanup();
}