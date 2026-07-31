import json
import time
import config
from mqtt_services import mqtt_client

def publish_test_telemetry():
    payload = {
        "soc":{
                "value": 80,
                "action": 0,
             },
        "ac_output": {
            "value": 0,
            "action": 0,
        },
        "dc_output":{
            "value": 0,
            "action": 0, 
        },
        "ac_schedule":{
            "value": 0,
            "action": 0, # 0 for reading, 1 for writing
        },
}

    mqtt_client.publish(
        config.TOPIC_TELEMETRY,
        json.dumps(payload)
    )

while True:
    publish_test_telemetry()
    time.sleep(1)