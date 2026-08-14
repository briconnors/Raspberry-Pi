//Summary of main.cpp: pull payload, initialize program, for now testing MQTT linkage but 
//later main controls loop 

#include <chrono> //timing, delays, and intervals
#include <iostream> //terminal printing
#include <thread>//parallel file running or sleep scheduling, each thread acts as a seperate line 
                 //for the different parts of the controller to listen to at differing intervals 
                 //(ie polling constantly vs scheduled wake timing every x seconds)
#include "config.h"//saved constants to reference (broker ip, topics, limits, device name)
#include "mqtt_client.h"//declares mqtt helper functions used by main.cpp
#include "controller.h"//declares the controller class and its functions


//entry point of program to begin control loop:
int main(){
    std::cout << "STARTING CONTROLLER" << std::endl;
    Controller controller;//create the state machine object to hold the current state of the system
    controller.SetGridOffsetDemand(500.0); //(Watts) temporary hardcoded requested grid offset, in the future should be replaced with ML or Con-ed Signal
    controller.Initialize();//initialize the controller and all its components
    int loopCounter = 0; //counter to keep track of how many times the loop has run, for debugging purposes

    while(loopCounter<10){//infinite loop to keep the program running, for now just testing MQTT connection
        controller.Run();//run the controller state machine, which will handle all the logic and transitions
        std::this_thread::sleep_for(std::chrono::seconds(2));//wait for 1 second before next iteration
        loopCounter ++; //add one loop to the counter for prototyping
    }

    //for inside run loop eventually
    controller.PrintState();
    //networkInterface.PrintNetworkConditions();

    DisconnectMqtt();//disconnect from the broker after running once successfully
    
}   

//MQTT test function to send a command to the plug, for now just testing the connection
void PlugTest(){
    std::cout << "Starting plug test!" << std::endl;
    if (!ConnectMqtt()){
        std::cerr << "Failed to connect to MQTT." << std::endl;
        return;
    }
    if (!PublishMessage(TOPIC_CMD_POWER, "ON")){
        std::cerr << "Failed to send ON command." << std::endl;
        return;
    }
    std::cout << "Plug command sent!" << std::endl;
}

//for testing:
//mosquitto_pub -h 127.0.0.1 -p 1883 -t cmnd/plug1/POWER -m ON
//mosquitto_pub -h 127.0.0.1 -p 1883 -t cmnd/plug1/POWER -m OFF