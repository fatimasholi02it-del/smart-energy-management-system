import json
import paho.mqtt.client as mqtt

BROKER_HOST = "localhost"
BROKER_PORT = 1883
TOPIC = "energy/readings"

payload = {
    "device_id": "simulator_01",
    "room_id": "room_1",
    "energy": 3.2,
    "timestamp": "2026-06-29T12:45:00",
    "signature": "fake-invalid-signao"
}

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(BROKER_HOST, BROKER_PORT, 60)

message = json.dumps(payload)
result = client.publish(TOPIC, message)

if result.rc == 0:
    print("Tampered message sent successfully.")
    print(message)
else:
    print("Failed to send tampered message.")