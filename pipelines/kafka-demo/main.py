import os
import sys
import typing
import logging
import pandas as pd
import apache_beam as beam
from dotenv import load_dotenv
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.io.kafka import ReadFromKafka, WriteToKafka, default_io_expansion_service

"""This is a sample pipeline that reads from a list of Kafka topics,
converts the message to upper case, and sends it out to an output topic.
"""

load_dotenv()

CONSUMER_TOPICS = ["test"]
PRODUCER_TOPIC  = "test2"
CONSUMER_CONFIG = {"bootstrap.servers":os.getenv("BOOTSTRAP_SERVER")}

#https://github.com/apache/beam/issues/20979
KAFKA_EXPANSION_SERVICE = default_io_expansion_service(
                            append_args=[
                                "--defaultEnvironmentType=PROCESS",
                                "--defaultEnvironmentConfig={\"command\":\"/opt/apache/beam_java/boot\"}",
                                "--experiments=use_deprecated_read"
                            ]
                        )

def processMessage(message):
    """Converts a Kafka message to upper case."""
    try:
        return ('test'.encode("utf-8"), str(message[1].decode("utf-8")).upper().encode("utf-8"))
    except Exception as e:
        logging.ERROR('Error converting message: ' + str(e))
        return ('test'.encode("utf-8"), 'ERROR'.encode("utf-8"))
    
def runPipeline(options):
    pipeline_options = PipelineOptions(options)

    with beam.Pipeline(options=pipeline_options) as p:

        # msgs = (p | "Read from Kafka" >> ReadFromKafka(consumer_config=CONSUMER_CONFIG, topics=CONSUMER_TOPICS, expansion_service=KAFKA_EXPANSION_SERVICE)
        #           | "Process message" >> beam.Map(processMessage).with_output_types(typing.Tuple[bytes, bytes])
        # )

        # msgs | "Write to Kafka" >> WriteToKafka(producer_config=CONSUMER_CONFIG, topic=PRODUCER_TOPIC, expansion_service=KAFKA_EXPANSION_SERVICE)
        # msgs | "Log messages" >> beam.Map(lambda x: logging.info(x))

        msgs = (p | "Read from Kafka" >> ReadFromKafka(consumer_config=CONSUMER_CONFIG, topics=CONSUMER_TOPICS, expansion_service=KAFKA_EXPANSION_SERVICE)
                  | "Process message" >> beam.Map(processMessage).with_output_types(typing.Tuple[bytes, bytes])
                  | "Write to Kafka" >> WriteToKafka(producer_config=CONSUMER_CONFIG, topic=PRODUCER_TOPIC, expansion_service=KAFKA_EXPANSION_SERVICE)
        )

if __name__ == '__main__':

    args = [
        "--sdk_worker_parallelism=1",
        "--streaming",
        "--environment_type=PROCESS",
        "--environment_config={\"command\": \"/opt/apache/beam/boot\"}"
    ]

    args.extend(sys.argv[1:])
    runPipeline(args)