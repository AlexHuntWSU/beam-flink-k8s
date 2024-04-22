import sys
import json
import time
import typing
import socket
import logging
import requests
import subprocess

FLINK_CLUSTER = 'flink-session-rest:8081'
SAVEPOINTS_DIR = '/flink-data/savepoints'
JAR_PATH = '/jars/beam-runners-flink-1.16-job-server-2.49.0.jar'

def run_job_server(jar_path: str, flink_cluster: str) -> typing.Type[subprocess.Popen]:
    """Starts up a job server using a local jar file. By default, the job service
    will be started on localhost:8099.

    :param jar_path: Local path to the job server jar file.
    :param flink_cluster: Address of the Flink cluster.
    """
    job_server = f"java -jar {jar_path} --flink-master={flink_cluster}"
    return subprocess.Popen(job_server, 
                            shell=True, 
                            stdout=sys.stdout, 
                            stderr=subprocess.STDOUT)

def get_job_id(job_name: str) -> list:
    """Returns job info based on the job name. Returns a summary
    of every job with the matching name.
    
    :param job_name: Name of the Flink job.
    """
    url = f'http://{FLINK_CLUSTER}/v1/jobs/overview'
    response = requests.get(url).json()
    matching_jobs = []
    for job in response['jobs']:
        if job['name'] == job_name:
            matching_jobs.append(job)
    return matching_jobs

def initiate_savepoint(job_id: str, 
                       savepoints_dir: str=SAVEPOINTS_DIR, 
                       cancel: bool=False) -> str:
    """Creates a savepoint for a job. Can optionally cancel
    the job.
    
    :param job_id: Id of the Flink job.
    :param savepoint_path: Directory where the savepoints are saved.
    :param cancel: If true, the job will be cancelled.
    """
    url = f'http://{FLINK_CLUSTER}/v1/jobs/{job_id}/savepoints'
    data = {"cancel-job": cancel, 
            "formatType": "NATIVE", 
            "target-directory": savepoints_dir}
    response = requests.post(url=url, json=data).json()
    return response['request-id']

def check_savepoint_status(job_id: str, request_id: str) -> dict:
    """Checks the status of a savepoint request.
    
    :param job_id: Id of the Flink job.
    :param request_id: Identifier of a savepoint request.
    """
    url = f'http://{FLINK_CLUSTER}/v1/jobs/{job_id}/savepoints/{request_id}'
    response = requests.get(url).json()
    return response

def check_uploads(job_name: str,
                  job_id: str=None,
                  invalid_status: list=['FINISHED', 'CANCELED', 'FAILED'],
                  retries: int=5) -> bool:
    """Checks if a job has successfully been submitted to
    the cluster.
    
    :param job_name: Name of the submitted job.
    :param job_id: Id of the job to exclude. This is used when
        updating from a savepoint as it will inaccurately
        assume the job was submitted.
    :param invalid_status: Job statuses to exclude when
        verifying that the job has been submitted.
    :param retries: Number of retries to check the API.
        Only applies if the API returns an error.
    """
    for i in range(0, retries):
        try:
            response = get_job_id(job_name)
            for job in response:
                if job['state'] not in invalid_status and job['jid'] != job_id:
                    return True
                else:
                    pass
            return False
        except:
            pass
    return False

def create_savepoint(job_id: str, 
                     savepoints_dir: str=SAVEPOINTS_DIR, 
                     cancel: bool=False, 
                     timeout: int=300) -> str:
    """Creates and validates a savepoint. Returns the path
    if the savepoint was successful.
    
    :param job_id: Id of the Flink job.
    :param savepoint_path: Directory where the savepoints are saved.
    :param cancel: If true, the job will be cancelled.
    :param timeout: Time to wait for a successful savepoint status.
    """
    savepoint = initiate_savepoint(job_id, savepoints_dir, cancel)
    t = time.time()
    while True:
        status = check_savepoint_status(job_id, savepoint)
        try:
            return status['operation']['location'].split(':')[-1]
        except:
            pass

        if time.time() - t >= timeout:
            logging.error('Savepoint request failed: Savepoint timed out')
            break
    return None

def create_job(config: dict, job_id: str=None, timeout: int=600) -> None:
    """Submits a new job to the Flink cluster.
    
    :param config: Job request.
    :param job_id: Id of the job to exclude. This is used when
        updating from a savepoint as it will inaccurately
        assume the job was submitted.
    :param timeout: Time to wait for the job to be submitted.
    """
    p = subprocess.Popen(config['command'], 
                         shell=True, 
                         stdout=sys.stdout, 
                         stderr=subprocess.STDOUT)
    t = time.time()

    while True:
        if check_uploads(config['name'], job_id):
            logging.info('Job uploaded')
            break
        elif time.time() - t >= timeout:
            logging.error('Job creation failed: Job upload timed out')
            break
        else:
            time.sleep(10)
    
    p.terminate()
    return None

def upgrade_job(config: dict) -> None:
    """Upgrades a job by stopping and re-uploading the job.
    
    :param config: job request.
    """
    # Gets the running job, there should only be one.
    #TODO: Error handling on multiple running jobs.
    jobs = get_job_id(config['name'])
    for job in jobs:
        if job['state'] not in ['FINISHED', 'CANCELED', 'FAILED']:
            job_id = job['jid']

            if config['operation'] == 'STATEFUL_UPDATE' and '--savepoint_path' not in config['command']:
                savepoint_path = create_savepoint(job_id=job_id, cancel=True)
                if savepoint_path:
                    config['command'] = f"{config['command']} --savepoint_path={savepoint_path}"
                    create_job(config, job_id)
                else:
                    logging.error('Update operation failed: Could not restart from the latest savepoint')
            
            elif config['operation'] == 'STATEFUL_UPDATE' and '--savepoint_path' in config['command']:
                create_savepoint(job_id=job_id, cancel=True)
                create_job(config, job_id)

            elif config['operation'] == 'STATELESS_UPDATE' and '--savepoint_path' not in config['command']:
                create_savepoint(job_id=job_id, cancel=True) #TODO: Use the stop job endpoint to also allow draining
                create_job(config, job_id)

            else:
                logging.error('Update operation failed: Invalid upgrade operation')
        else:
            logging.error('Update operation failed: Job is not running on the cluster')
    return None
            
def submit_jobs(pipelines: list) -> None:
    """Submit pipelines to the Flink cluster.
    
    :param pipelines: List of job create/upload/delete requests.
    """
    upgrade_types = ['STATEFUL_UPDATE', 'STATELESS_UPDATE']
    for command in pipelines:
        # Check if the job is already running
        exists = check_uploads(command['name'])

        if command['operation'] == 'CREATE':
            if exists:
                logging.error('Job creation failed: Job has already been submitted to the cluster')
            else:
                create_job(command)

        elif command['operation'] in upgrade_types:
            if exists:
                upgrade_job(command)
            else:
                logging.error('Update operation failed: Job is not running on the cluster')

        elif command['operation'] == 'STOP':
            if exists:
                jobs = get_job_id(command['name'])
                for job in jobs:
                    create_savepoint(job_id=job['jid'], cancel=True)
            else:
                logging.error('Job cancellation failed: Job is not running on the cluster')
        
        elif command['operation'] == 'SAVEPOINT':
            if exists:
                jobs = get_job_id(command['name'])
                for job in jobs:
                    if job['state'] not in ['FINISHED', 'CANCELED', 'FAILED']:
                        create_savepoint(job_id=job['jid'])
                    else:
                        pass
        
        elif command['operation'] == 'SKIP':
            logging.info('Upload skipped')

        else:
            logging.error('Invalid operation')

    return None

def check_job_service_status(port: int=8099, host: str='localhost') -> bool:
    """Check if the job server is running.
    
    :param port: Port of the job server.
    :param host: Host of the job server.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0
    
def run_upload_process(pipelines: dict) -> None:
    """Starts a job service and uploads Apache Beam 
    pipelines to a Flink cluster.

    :param pipelines: List of job create/upload/delete requests.
    """
    x = run_job_server(JAR_PATH, FLINK_CLUSTER)

    timeout = 300
    t = time.time()
    while True:
        if check_job_service_status():
            break
        if time.time() - t >= timeout:
            x.terminate()
            logging.error("Job server failed to start")
    
    submit_jobs(pipelines)
    x.terminate()

    logging.info('Process complete')
    return None

if __name__ == "__main__":
    try:
        with open('/config/pipeline-submission.json', 'r') as f:
            pipelines = json.loads(f.read())
            run_upload_process(pipelines)
    except Exception as e:
        print(e)