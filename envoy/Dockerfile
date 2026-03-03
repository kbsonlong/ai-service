FROM envoyproxy/envoy:v1.24-latest

COPY envoy.yaml /etc/envoy/envoy.yaml

CMD ["/usr/local/bin/envoy", "-c", "/etc/envoy/envoy.yaml", "--service-cluster", "ai-service-gateway"]