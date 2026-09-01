# This project was developed with assistance from AI tools.

REGISTRY ?= quay.io/jary
TAG ?= latest
SERVICES := scenario-engine weather-service camera-simulator risk-engine defect-detector dispatch-optimizer console-backend growth-simulator
FRONTEND_DIR := console/frontend

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

.PHONY: build
build: $(addprefix build-,$(SERVICES))

.PHONY: build-%
build-%:
	podman build -f services/$*/Containerfile -t $(REGISTRY)/grid-resilience-$*:$(TAG) .

# ---------------------------------------------------------------------------
# Push
# ---------------------------------------------------------------------------

.PHONY: push
push: $(addprefix push-,$(SERVICES))

.PHONY: push-%
push-%:
	podman push $(REGISTRY)/grid-resilience-$*:$(TAG)

# ---------------------------------------------------------------------------
# Deploy / Undeploy (ArgoCD)
# ---------------------------------------------------------------------------

.PHONY: deploy
deploy:
	oc apply -f infrastructure/gitops/applications/

.PHONY: undeploy
undeploy:
	oc delete -f infrastructure/gitops/applications/ --ignore-not-found

# ---------------------------------------------------------------------------
# Local dev (docker-compose)
# ---------------------------------------------------------------------------

.PHONY: dev-up
dev-up:
	podman compose up -d

.PHONY: dev-down
dev-down:
	podman compose down

.PHONY: dev-logs
dev-logs:
	podman compose logs -f

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

.PHONY: seed
seed:
	python3 data/seed/load_seed_data.py

# ---------------------------------------------------------------------------
# Code quality
# ---------------------------------------------------------------------------

.PHONY: lint
lint:
	ruff check .
	ruff format --check .
	mypy services/common/grid_common \
		services/scenario-engine/scenario_engine \
		services/weather-service/weather_service \
		services/camera-simulator/camera_simulator \
		services/risk-engine/risk_engine \
		services/defect-detector/defect_detector \
		services/dispatch-optimizer/dispatch_optimizer \
		services/console-backend/console_backend \
		services/growth-simulator/growth_simulator
