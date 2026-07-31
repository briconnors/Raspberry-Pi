# mqtt_service.py: establishes client/broker connection and parses/constructs payloads
import json # allow payloads to be written in strings
import paho.mqtt.client as mqtt # establish the python script as a client of the broker
import config
import bluetti_services
import time

# establish a client to pair to broker:
mqtt_client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2
)
# enter credentials manually for now:
mqtt_client.username_pw_set(
    config.MQTT_USER,
    config.MQTT_PASSWORD
)
# connect the new client to the broker:
mqtt_client.connect(
    config.MQTT_HOST,
    config.MQTT_PORT
)

mqtt_client.loop_start() # start the background network loop 

# stores the result of the most recent action performed on the battery
# so the controller knows if the last command succeeded/failed
class ActuatorState:
    def __init__(self):
        # default values until a command changes them
        self.request = "read" # overwrite with write/read
        self.value = None # no value being written/read
        self.action = True # overwrite with true/false
        self.flag = "success" # overwrite with success/fail

actuator = ActuatorState()

# publish on one MQTT stream for the telemetry (bluetti/ac200/telemetry):
def json_publish_battery_state(value, state, actuator): #in state: 0 for reading, 1 for writing
    # construct the JSON packet before converting it into a string
    payload = {
        "device":"bluetti_ac200",
        "timestamp": time.time(),
        "action": { # action defined as read write or none
                    "request": actuator.request, # what the controller wants to be written/read
                    "value": actuator.value, # what is being written/read (for validation)
                    "status": actuator.action, # action defined as read write or none
                    "state": actuator.flag # success or failure of ble coms
        },
        "telemetry":{
            "home_telemetry": {
                "soc": value.soc,
                "voltage": value.voltage,
                "current": value.current,
                "pv_watts": value.pv_watts,
            },

            "ac_output": {
                    "value": value.ac_output,
                    "action": state.ac_output,
            },
            "ac_input": {
                    "value": value.ac_input,
                    "action": state.ac_input,
            },
            "ac_input_setting": {
                    "value": value.ac_input_setting,
                    "action": state.ac_input_setting,
            },
            "dc_output": {
                    "value": value.dc_output,
                    "action": state.dc_output,
            },
            "dc_input": {
                    "value": value.dc_input,
                    "action": state.dc_input,
            }
        }
    }
    # convert the dictionary into JSON and publish it to the broker
    return mqtt_client.publish(
    config.TOPIC_TELEMETRY,
    json.dumps(payload)
    )
# serialize schedule data into JSON, placeholder until scheduling is finished
def json_publish_battery_schedule(request, value, action, flag): #in state: 0 for reading, 1 for writing
    payload = {
        "device":"bluetti_ac200",
        "timestamp": time.time(),
        "action": {
                    "request": request, # what the controller wants to be written/read
                    "value": value, # what is being written/read (for validation)
                    "status": action, # action defined as read write or none
                    "state": flag # success or failure of ble coms
                },
        "schedule":{
            
        }
    }
    
    # serialize the dictionary into JSON and publish it to the telemetry topic
    return mqtt_client.publish(
        config.TOPIC_TELEMETRY,
        json.dumps(payload)
    )

# call in loop.py with:
#parsed = mqtt_service.latest_parsed
#if parsed is not None:
    #mqtt_service.update_battery_state(
        #parsed,
        #value,
        #state,)
# shared state updated by MQTT callbacks loop.py can read these
latest_parsed = None
latest_command = None
# callback executed whenever a subscribed topic receives a new MQTT message
def on_message(client, userdata, msg):
    global latest_parsed
    global latest_command

    if msg.topic == config.TOPIC_TELEMETRY:
        latest_parsed = json_process_telemetry(msg)

    elif msg.topic == config.TOPIC_COMMAND:
        latest_command = json_process_command(msg)

        # later:
        # send this command to loop.py

#call : parsed = json_process_telemetry(msg)

# deserialize an incoming telemetry packet back into a Python dictionary that is easier to work with
def json_process_telemetry(msg):
 # action defined as read write or none
    if not msg.payload:
        return None # ignore empty packets
    payload = json.loads(msg.payload)
    # safely retrieve nested dictionaries, .get() avoids exceptions if a field is missing
    telemetry = payload.get("telemetry",{})
    action = payload.get("action",{})
    home = telemetry.get("home_telemetry",{})
    # flatten the nested JSON into something easier to access throughout the rest of the program
    return {
        "action": {
            "request": action.get("request"),
            "value": action.get("value"),
            "status": action.get("status"),
            "state": action.get("state")
        },
        "soc": home.get("soc"),
        "voltage": home.get("voltage"),
        "current": home.get("current"),
        "pv_watts": home.get("pv_watts"),

        "AC output": telemetry.get("ac_output"),
        "AC input": telemetry.get("ac_input"),
        "AC input setting": telemetry.get("ac_input_setting"),
        "DC output": telemetry.get("dc_output"),
        "DC input": telemetry.get("dc_input"),
    }

# deserialize an incoming controller command
def json_process_command(msg):
    if not msg.payload:
        return None
    payload = json.loads(msg.payload)
    return {
        "request": payload.get("request"),
        "target": payload.get("target"),
        "value": payload.get("value"),
    }

#print(f"[READ] {label}: {values}", flush=True)

#for inside main py loop:


#if command is not None:
# if command["request"] == "read":
# continue polling
#if action == "write":
# perform ble write

# copy values from the parsed JSON into the battery objects so the rest of the program always uses newest data
def update_battery_state(parsed, value, state):

    value.soc = parsed["soc"]
    value.voltage = parsed["voltage"]
    value.current = parsed["current"]
    value.pv_watts = parsed["pv_watts"]

    value.ac_output = parsed["AC output"]["value"]
    state.ac_output = parsed["AC output"]["action"]

    value.ac_input = parsed["AC input"]["value"]
    state.ac_input = parsed["AC input"]["action"]

    value.ac_input_setting = parsed["AC input setting"]["value"]
    state.ac_input_setting = parsed["AC input setting"]["action"]

    value.dc_output = parsed["DC output"]["value"]
    state.dc_output = parsed["DC output"]["action"]

    value.dc_input = parsed["DC input"]["value"]
    state.dc_input = parsed["DC input"]["action"]

# register the callback and listen for both telemetry and controller command topics
mqtt_client.on_message = on_message

mqtt_client.subscribe(config.TOPIC_TELEMETRY)
mqtt_client.subscribe(config.TOPIC_COMMAND)