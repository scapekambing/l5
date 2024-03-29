from __future__ import absolute_import
from __future__ import print_function
import argparse
from awscrt import io, mqtt, auth, http
from awsiot import mqtt_connection_builder
import sys
import threading
import time
import signal

io.init_logging(getattr(io.LogLevel, io.LogLevel.NoLogs.name), 'stderr')

received_count = 0
received_all_event = threading.Event()

# Callback when connection is accidentally lost.


def on_connection_interrupted(connection, error, **kwargs):
    print("Connection interrupted. error: {}".format(error))


# Callback when an interrupted connection is re-established.
def on_connection_resumed(connection, return_code, session_present, **kwargs):
    print("Connection resumed. return_code: {} session_present: {}".format(
        return_code, session_present))

    if return_code == mqtt.ConnectReturnCode.ACCEPTED and not session_present:
        print("Session did not persist. Resubscribing to existing topics...")
        resubscribe_future, _ = connection.resubscribe_existing_topics()

        # Cannot synchronously wait for resubscribe result because we're on the connection's event-loop thread,
        # evaluate result with a callback instead.
        resubscribe_future.add_done_callback(on_resubscribe_complete)


def on_resubscribe_complete(resubscribe_future):
    resubscribe_results = resubscribe_future.result()
    print("Resubscribe results: {}".format(resubscribe_results))

    for topic, qos in resubscribe_results['topics']:
        if qos is None:
            sys.exit("Server rejected resubscribe to topic: {}".format(topic))

# MESSAGE RECEIVED
# Callback when the subscribed topic receives a message


def on_message_received(topic, payload, **kwargs):
    print("\nMessage Received: {}\n".format(payload.decode("utf-8")))
    received_all_event.set()


# Spin up resources
event_loop_group = io.EventLoopGroup(1)
host_resolver = io.DefaultHostResolver(event_loop_group)
client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

# create the MQTT connection

endpoint = "YOUR ENDPOINT API"
cert_filepath = "thing2-cert.pem.crt"
pri_key_filepath = "thing2-private-key.pem.key"
ca_filepath = "aws-root-cert.pem"
client_id = "raspberry-pi"

mqtt_connection = mqtt_connection_builder.mtls_from_path(
    endpoint=endpoint,
    cert_filepath=cert_filepath,
    pri_key_filepath=pri_key_filepath,
    client_bootstrap=client_bootstrap,
    ca_filepath=ca_filepath,
    on_connection_interrupted=on_connection_interrupted,
    on_connection_resumed=on_connection_resumed,
    client_id=client_id,
    clean_session=False,
    keep_alive_secs=6)

print("Connecting to {} with client ID '{}'...".format(endpoint, client_id))

connect_future = mqtt_connection.connect()

# Waits until a result is available
connect_future.result()
print("Connected!")


# STUDY THE CODE FROM HERE
# *******************************

my_own_topic = "output"
the_other_topic = "readings"


# subscribe to topic
print("Listening to '{}' topic...".format(my_own_topic))
subscribe_future, packet_id = mqtt_connection.subscribe(
    topic=my_own_topic,
    qos=mqtt.QoS.AT_LEAST_ONCE,
    callback=on_message_received)

subscribe_result = subscribe_future.result()

print("Publishing to '{}' topic...\n".format(the_other_topic))
print("Enter your messages (press Ctrl-C to finish):")

# Infinite loop for sending messages
with open('readings.txt', 'r') as file:  # open txt file containing sensor readings
    line = file.readline()  # read first line
    while line:  # enter while loop
        try:
            msg = line.strip()  # remove white spaces
            mqtt_connection.publish(  # publish to readings
                topic=the_other_topic,
                payload=msg,
                qos=mqtt.QoS.AT_LEAST_ONCE)
            print('Sending: ', msg)
            time.sleep(2)  # delay for 2s
            line = file.readline()  # read next line

        # Interrupt with Ctrl-C
        except(KeyboardInterrupt, SystemExit):
            break


# Disconnect
print("Disconnecting...")
disconnect_future = mqtt_connection.disconnect()
disconnect_future.result()
print("Disconnected!")
