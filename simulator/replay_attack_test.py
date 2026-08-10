import json
import paho.mqtt.client as mqtt

BROKER_HOST = "localhost"
BROKER_PORT = 1883
TOPIC = "energy/readings"

payload = {
    "device_id": "simulator_01",
    "room_id": "room_1",
    "energy": 3.41,
    "timestamp": "2026-06-30T16:07:35.857749",
    "signature": "46c561c6f037c3a36876279365be5aeccddf46af7bbf8c32e05a182f8ab396f5"
}

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(BROKER_HOST, BROKER_PORT, 60)

message = json.dumps(payload)
result = client.publish(TOPIC, message)

if result.rc == 0:
    print("Replay message sent successfully.")
    print(message)
else:
    print("Failed to send replay message.")
