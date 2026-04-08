FROM debian:bookworm-slim

# Install CA certificates to ensure the toolbox can make secure outbound connections
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the binary and your configuration file into the container
COPY toolbox .
COPY tools.yaml .

# Ensure the binary has execution permissions
RUN chmod +x ./toolbox

# The command now includes --address 0.0.0.0 to allow traffic from outside the container
CMD ["./toolbox", "--tools-file", "tools.yaml", "--port", "8080", "--address", "0.0.0.0", "--ui" , "--enable-api"]

# Inform Docker that the container listens on port 8080
EXPOSE 8080
