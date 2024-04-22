# beam-flink-k8s

POC for running Apache Beam pipelines on the Flink runner using the Flink Kubernetes Operator.

## Prerequsites

Docker, Kubernetes, and Helm

### Flink Kubernetes Operator

Install the certificate manager on the Kubernetes cluster.

```console
kubectl create -f https://github.com/jetstack/cert-manager/releases/download/v1.8.2/cert-manager.yaml
```

Deploy the Flink Kubernetes Operator Helm chart.

```console
helm repo add flink-operator-repo https://downloads.apache.org/flink/flink-kubernetes-operator-1.8.0/
helm install flink-kubernetes-operator flink-operator-repo/flink-kubernetes-operator
```

## Submitting the Apache Beam Pipelines

Build the docker image. This will include Flink, Beam pipelines, and the Beam SDK workers.

```console
docker build -f Dockerfile.flink -t beam .
```

### Option #1 (Application mode)

In application mode, the job is submitted along with the Flink cluster. In this case, 
the cluster will only run and manage the one job. This provides resource isolation
and easier deployments at the cost of an additional overhead of spinning up a job manager
for every pipeline.

Start the cluster and submit the Flink/Beam job:

```console
kubectl apply -f flink-application.yaml
```

### Option #2 (Session mode)

In session mode, we start up a long running Flink cluster than can accept multiple jobs. This is done using either the cluster's REST API, UI, or with a Job deployment on the Flink Kubernetes Operator. 

For Apache Beam pipelines written in Python, the options are limited as there is no executable jar file that the previous options expect. For both session and application mode, the Apache Beam's job server is used to submit our jobs.

```console
kubectl apply -f flink-session.yaml
```

Next, we define our jobs and cluster operations in the pipeline-submission.json file. Run the following command to create a Kubernetes configmap. This will mount the json on the launch environment.

```console
kubectl create configmap config --from-file pipeline-submission.json -o yaml --dry-run=client | kubectl apply -f -
```

Finally, we create our launch environment. This is used to create, update, and delete the pipelines.

```console
kubectl apply -f launch-environment.yaml
```

### Shutdown

```console
kubectl delete -f flink-application.yaml
kubectl delete -f flink-session.yaml
```

## Flink UI

With the NodePort service, the cluster's UI and REST API can be accessed at localhost:30032. Optionally, run the following command to directly expose the Flink port.

```console
kubectl port-forward svc/flink-session-rest 8081
```

## Flink API

Here is an example of using the Flink's REST API to create a savepoint for the pipeline.

```python
import requests

job = 'e581e973a601cb86693791c3b152d564'
url = f'http://localhost:30032/v1/jobs/{job_id}/savepoints'
data = {"cancel-job": False, "target-directory": "/flink-data/savepoints"}

response = requests.request(method="POST", url=url, json=data)
print(response.text)
```