# Grid Resilience Operations Center — Deployment Guide

> [!NOTE]
> This project was developed with assistance from AI tools.

## Prerequisites

### Cluster

- OpenShift 4.x cluster (tested on OpenShift Dedicated)
- At least 3 untainted worker nodes with ~4 CPU allocatable each
- GPU nodes: L40S (CorrDiff + vLLM) and L4 (cuOpt) with NVIDIA GPU Operator installed

### Operators

Install from OperatorHub, wait for "Succeeded" status on each:

1. NVIDIA GPU Operator
2. AMQ Streams (or Strimzi for dev)
3. Crunchy Postgres for Kubernetes (PGO)
4. Red Hat OpenShift GitOps (Argo CD)

### Accounts

- NVIDIA NGC account with API key
- HuggingFace account with access approved for [nvidia/Cosmos-Reason2-8B](https://huggingface.co/nvidia/Cosmos-Reason2-8B) (gated model — must accept license agreement)
- HuggingFace access token — must be from the **same account** that accepted the license



### CPU pressure on worker nodes

RHOAI (OpenShift AI) components can consume ~8 CPU in requests across worker nodes. If pods fail to schedule with `Insufficient cpu`, scale down unused RHOAI deployments:

```bash
oc scale deployment rhods-dashboard -n redhat-ods-applications --replicas=0
oc scale deployment notebook-controller-deployment -n redhat-ods-applications --replicas=0
oc scale deployment mlflow-operator-controller-manager -n redhat-ods-applications --replicas=0
oc scale deployment kserve-controller-manager -n redhat-ods-applications --replicas=0
oc scale deployment odh-notebook-controller-manager -n redhat-ods-applications --replicas=0
oc scale deployment data-science-pipelines-operator-controller-manager -n redhat-ods-applications --replicas=0
oc scale deployment model-registry-operator-controller-manager -n redhat-ods-applications --replicas=0
oc scale deployment odh-model-controller -n redhat-ods-applications --replicas=0
oc scale deployment dashboard-redirect -n redhat-ods-applications --replicas=0
oc scale deployment model-catalog -n rhoai-model-registries --replicas=0
oc scale deployment model-catalog-postgres -n rhoai-model-registries --replicas=0
```

The RHOAI operator may attempt to scale these back up. If so, scale down the operator itself or adjust its configuration.

---



## Step 1: Fork and update repo URLs

Fork `https://github.com/RHPhysicalAI/grid-resilience-showcase` to your own GitHub account.

All GitOps YAML files reference the source repo URL. Update them all:

```bash
find infrastructure/gitops -name "*.yaml" \
  -exec sed -i 's|https://github.com/jeremyary/grid-resilience-showcase.git|https://github.com/<your-org>/grid-resilience-showcase.git|g' {} \;
```

Verify no old references remain:

```bash
grep -r "jeremyary" infrastructure/gitops/
```

Commit and push to your fork.

---



## Step 2: Create namespaces and secrets

```bash
# Create all 4 namespaces
oc apply -f infrastructure/cluster/namespaces.yaml

# NGC API key (CorrDiff NIM)
oc -n grid-ops-ai create secret generic ngc-api-key \
  --from-literal=NGC_API_KEY=<your-ngc-key>

# NGC pull secret (nvcr.io container images)
oc -n grid-ops-ai create secret docker-registry ngc-pull-secret \
  --docker-server=nvcr.io \
  --docker-username=\$oauthtoken \
  --docker-password=<your-ngc-key>

# HuggingFace token (Cosmos Reason model download)
# IMPORTANT: must be from the account that accepted the Cosmos-Reason2-8B license
oc -n grid-ops-ai create secret generic hf-token \
  --from-literal=token=<your-hf-token>

# Coturn TLS cert (self-signed for WebRTC TURN relay)
openssl req -x509 -newkey rsa:2048 \
  -keyout /tmp/tls.key -out /tmp/tls.crt \
  -days 365 -nodes -subj "/CN=coturn"
oc create secret tls coturn-tls -n grid-ops-ai \
  --cert=/tmp/tls.crt --key=/tmp/tls.key

# Coturn auth
oc create secret generic coturn-auth -n grid-ops-ai \
  --from-literal=password=gridops
```

---



## Step 3: Create AppProject and grant Argo CD permissions

```bash
# AppProject defines allowed namespaces and source repos
oc apply -f infrastructure/gitops/projects/grid-ops.yaml

# Grant Argo CD permission to create Kafka, PostgreSQL, and OpenShift resources
oc adm policy add-cluster-role-to-user cluster-admin \
  system:serviceaccount:openshift-gitops:openshift-gitops-argocd-application-controller
```

---



## Step 4: Bootstrap Argo CD

```bash
oc apply -f infrastructure/gitops/bootstrap/root-application.yaml
```

This single command deploys everything via sync waves:


| Wave | Components                                                                         |
| ---- | ---------------------------------------------------------------------------------- |
| 0    | Operator subscriptions                                                             |
| 1    | Kafka cluster (3 brokers, KRaft), PostgreSQL, 14 Kafka topics                      |
| 2    | CorrDiff NIM (L40S), vLLM Cosmos Reason (L40S), cuOpt (L4), Kit substation, Coturn |
| 3    | weather-service, risk-engine, defect-detector, scenario-engine, camera-simulator   |
| 4    | dispatch-optimizer, console-backend, console-frontend                              |


Monitor progress:

```bash
oc get applications -n openshift-gitops -w
```

Wait for all applications to show `Synced`. Some will show `Degraded` or `Missing` until the secrets and database steps below are completed.

**Important:** Complete Steps 5 and 6 as soon as PostgreSQL is running (wave 1). Services in waves 3-4 depend on the Postgres secret and database schema. If they start before those are ready, their Kafka consumer threads will crash silently — health checks pass but no events are processed. If this happens, restart the affected pods after completing Steps 5 and 6:

```bash
oc delete pods -l app.kubernetes.io/part-of=grid-resilience -n grid-ops-services
oc delete pods -l app.kubernetes.io/part-of=grid-resilience -n grid-ops-console
```

---



## Step 5: Copy Postgres secret to service namespaces

Crunchy PGO creates the database credentials secret in `grid-ops-infra`, but services in other namespaces need it:

```bash
oc get secret grid-postgres-pguser-gridops -n grid-ops-infra -o yaml > /tmp/pg-secret.yaml

sed 's/namespace: grid-ops-infra/namespace: grid-ops-services/' /tmp/pg-secret.yaml | oc apply -f -
sed 's/namespace: grid-ops-infra/namespace: grid-ops-console/' /tmp/pg-secret.yaml | oc apply -f -
```

Services that were in `CreateContainerConfigError` will recover automatically.

---



## Step 6: Apply database schema and seed data

```bash
# Get the Postgres password
oc get secret grid-postgres-pguser-gridops -n grid-ops-infra \
  -o jsonpath='{.data.password}' | base64 -d && echo

# Grant schema creation permissions to the gridops user
oc exec -n grid-ops-infra <postgres-pod-name> \
  -c database -- psql -U postgres -d gridops \
  -c "GRANT ALL ON SCHEMA public TO gridops;"

# Find the Postgres pod name
oc get pods -n grid-ops-infra -l postgres-operator.crunchydata.com/role=master

# Port forward to Postgres
oc port-forward -n grid-ops-infra pod/<postgres-pod-name> 5432:5432 &

# Install psycopg if not already installed
pip3 install psycopg[binary]

# Apply schema (wait for port-forward to establish)
sleep 2 && python3 data/seed/apply_schema.py \
  "postgresql://gridops:<password>@localhost:5432/gridops?sslmode=require"

# Load seed data
python3 data/seed/load_seed_data.py \
  "postgresql://gridops:<password>@localhost:5432/gridops?sslmode=require"
```

Expected output:

```
Feeders:  4
Assets:   100
Segments: 80
Switches: 4
Cameras:  9
Crews:    8
Seed data loaded.
```

---



## Step 7: Seed the CorrDiff cache

After the weather-service and CorrDiff NIM are running:

```bash
oc port-forward -n grid-ops-services svc/weather-service 8180:8080 &
sleep 2 && curl -X POST http://localhost:8180/forecast/run
```

Takes ~45 seconds for live CorrDiff inference. Expected response:

```json
{"status":"published","forecast_hours":[0],"grid_cells":1242}
```

Subsequent scenario starts use the cached result for instant replay.

---



## Step 8: Access the console

```bash
oc get route console-frontend -n grid-ops-console -o jsonpath='{.spec.host}' && echo
```

Open the URL in a browser.

---



## Verification

Check that all pods are running:

```bash
oc get pods -n grid-ops-infra      # Kafka (3 brokers) + PostgreSQL
oc get pods -n grid-ops-ai         # CorrDiff, vLLM, cuOpt, Coturn
oc get pods -n grid-ops-services   # All microservices
oc get pods -n grid-ops-console    # Frontend + backend
```

Check Argo CD application status:

```bash
oc get applications -n openshift-gitops
```

All applications should show `Synced` / `Healthy` except `kit-substation` (see Known Issues).

---



## Scale down / Scale up



### Scale down (save GPU resources when not demoing)

```bash
oc scale deployment/corrdiff-nim deployment/vllm-cosmos deployment/cuopt deployment/kit-substation deployment/coturn -n grid-ops-ai --replicas=0
oc scale deployment/weather-service deployment/scenario-engine deployment/camera-simulator deployment/defect-detector deployment/dispatch-optimizer deployment/risk-engine -n grid-ops-services --replicas=0
oc scale deployment/console-backend deployment/console-frontend -n grid-ops-console --replicas=0
```



### Scale up

```bash
oc scale deployment/corrdiff-nim deployment/vllm-cosmos deployment/cuopt deployment/kit-substation deployment/coturn -n grid-ops-ai --replicas=1
oc scale deployment/weather-service deployment/scenario-engine deployment/camera-simulator deployment/defect-detector deployment/dispatch-optimizer deployment/risk-engine -n grid-ops-services --replicas=1
oc scale deployment/console-backend deployment/console-frontend -n grid-ops-console --replicas=1
```

---



## Known Issues


| Issue                                     | Status        | Notes                                                                                                                                                                                |
| ----------------------------------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Kit substation `ImagePullBackOff`         | Expected      | Image `kit-substation:high` contains purchased 3D assets. Must be built from Fab asset pack (~$30-$70) or obtained from the original developer. Demo runs without the 3D twin panel. |
| Kafka version must be 4.1.0+              | Fixed in repo | AMQ Streams 3.2 does not support Kafka 4.0.0.                                                                                                                                        |
| vLLM needs HF token written as file       | Fixed in repo | Init container writes token to `$HF_HOME/token` for transformers library compatibility.                                                                                              |
| Weather-service missing `/cache` volume   | Fixed in repo | Added emptyDir volume mount for CorrDiff output caching.                                                                                                                             |
| `apply_schema.py` did not exist           | Added to repo | Database schema must be applied before seed data can be loaded.                                                                                                                      |
| Postgres user lacks schema permissions    | Manual step   | Run `GRANT ALL ON SCHEMA public TO gridops;` via exec into postgres pod.                                                                                                             |
| Postgres secret not in service namespaces | Manual step   | Must be copied from `grid-ops-infra` to `grid-ops-services` and `grid-ops-console`.                                                                                                  |
| Coturn secrets not pre-provisioned        | Manual step   | `coturn-tls` (TLS cert) and `coturn-auth` (password) must be created manually.                                                                                                       |
| Argo CD needs cluster-admin               | Manual step   | The application controller service account needs permission to create CRDs (Kafka, PostgresCluster, etc.).                                                                           |

---

## Code Changes vs Upstream

1. **`infrastructure/gitops/`** — All `repoURL` references updated to point to your fork
2. **`infrastructure/cluster/kafka-cluster.yaml`** — Kafka version bumped from 4.0.0 to 4.1.0
3. **`infrastructure/cluster/ai-workloads/vllm-cosmos.yaml`** — Added init container to write HF token to `$HF_HOME/token`
4. **`infrastructure/helm/weather-service/templates/deployment.yaml`** — Added `/cache` emptyDir volume mount
5. **`data/seed/apply_schema.py`** — New file: applies schema.sql via Python (psql may not be installed locally)
