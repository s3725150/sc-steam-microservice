
# -- Docker ------------------------------------------------------------

build-docker: ## Builds all required docker images
	docker build . -t gcr.io/cc-steam-chat/steam-ms -f Dockerfile

push-docker: ## Push Image into Container Registry
	docker push gcr.io/cc-steam-chat/steam-ms
