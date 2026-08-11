# json_serializer.py: establishes client/broker connection and parses/constructs payloads
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
        self.target = None # overwrite with command/telemetry target
        self.value = None # no value being written/read
        self.action = None # overwrite with true/false
        self.flag = "idle" # overwrite with success/fail

actuator = ActuatorState()

# publish on one MQTT stream for the telemetry (bluetti/ac200/telemetry):
def json_publish_battery_state(state_payload):
    print("Publishing telemetry...")
    payload = {
        "device": "bluetti_ac200",
        "timestamp": time.time(),
        "action": {
            "request": actuator.request,
            "target": actuator.target,
            "value": actuator.value,
            "status": actuator.action,
            "state": actuator.flag,
        },
        "telemetry": {
            "home_telemetry": {
                "soc": state_payload["soc"],
                "voltage": state_payload["voltage"],
                "current": state_payload["current"],
                "pv_watts": state_payload["pv_watts"],
                "grid_watts": state_payload["grid_watts"],
                "ac_watts": state_payload["ac_watts"],
                "dc_watts": state_payload["dc_watts"],
            },
            "dc_output": {
                "value": state_payload["dc_output"],
            },
            "ac_output": {
                "value": state_payload["ac_output"],
            },
            "dc_input": {
                "value": state_payload["dc_input"],
            },
            "ac_input": {
                "value": state_payload["ac_input"],
            },
            "grid_permission": {
                "value": state_payload["grid_permission"],
            },
            "ac_input_setting": {
                "value": state_payload["ac_input_setting"],
            },
        },
    }
    print(json.dumps(payload, indent=2))
    # convert the dictionary into JSON and publish it to the broker
    return mqtt_client.publish(
    config.TOPIC_TELEMETRY,
    json.dumps(payload)
    )
# serialize schedule data into JSON, placeholder until scheduling is finished
def json_publish_battery_schedule(request, value, action,state, flag): #in state: 0 for reading, 1 for writing
    payload = {
        "device":"bluetti_ac200",
        "timestamp": time.time(),
        "action": {
                    "request": request, # what the controller wants to be written/read
                    "target": actuator.target, # the target of the command
                    "value": value, # what is being written/read (for validation)
                    "status": action, # action defined as read write or none
                    "state": flag # success or failure of ble coms
                },
        "schedule":{
            "grid_charging_permission":{
                "value": value.grid_charging_permission,
                "action": state.grid_charging_permission,
            },
            "ac_input_setting": {
                    "value": value.ac_input_setting,
                    "action": state.ac_input_setting,
        }
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
latest_schedule = None
# callback executed whenever a subscribed topic receives a new MQTT message
def on_message(client, userdata, msg):
    global latest_parsed
    global latest_command
    global latest_schedule

    if msg.topic == config.TOPIC_TELEMETRY:
        latest_parsed = json_process_telemetry(msg)

    elif msg.topic == config.TOPIC_COMMAND:
        latest_command = json_process_command(msg)

    elif msg.topic == config.TOPIC_SCHEDULE:
        latest_schedule = json_process_schedule(msg)
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
            "target": action.get("target"),
            "value": action.get("value"),
            "status": action.get("status"),
            "state": action.get("state")
        },
        "soc": home.get("soc"),
        "voltage": home.get("voltage"),
        "current": home.get("current"),
        "pv_watts": home.get("pv_watts"),
        "grid_watts": home.get("grid_watts"),
        "ac_watts": home.get("ac_watts"),
        "dc_watts": home.get("dc_watts"),

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

def json_process_schedule(msg):
    if not msg.payload:
            return None
    payload = json.loads(msg.payload)
    return {
    "request": payload.get("request"),
    "charge_start": payload.get("charge_start"),
    "charge_end": payload.get("charge_end"),
    "discharge_start": payload.get("discharge_start"),
    "discharge_end": payload.get("discharge_end"),
}

#print(f"[READ] {label}: {values}", flush=True)

#for inside main py loop:


#if command is not None:
# if command["request"] == "read":
# continue polling
#if action == "write":
# perform ble write

# copy values from the parsed JSON into the battery objects so the rest of the program always uses newest data
def update_battery_state(parsed, value):

    value.soc = parsed["soc"]
    value.voltage = parsed["voltage"]
    value.current = parsed["current"]
    value.pv_watts = parsed["pv_watts"]
    value.grid_watts = parsed["grid_watts"]
    value.ac_watts = parsed["ac_watts"]
    value.dc_watts = parsed["dc_watts"]

    value.ac_output = parsed["AC output"]["value"]
    value.ac_input = parsed["AC input"]["value"]
    value.ac_input_setting = parsed["AC input setting"]["value"]
    value.dc_output = parsed["DC output"]["value"]
    value.dc_input = parsed["DC input"]["value"]

# register the callback and listen for both telemetry and controller command topics
mqtt_client.on_message = on_message

mqtt_client.subscribe(config.TOPIC_TELEMETRY)
mqtt_client.subscribe(config.TOPIC_COMMAND)
mqtt_client.subscribe(config.TOPIC_SCHEDULE)