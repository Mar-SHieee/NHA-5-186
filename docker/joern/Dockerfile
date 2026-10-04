# Base image with JDK (Joern runs on the JVM)
FROM eclipse-temurin:21-jdk

# System tools needed by the Joern installer:
#   curl + ca-certificates -> download over HTTPS
#   unzip                  -> unpack the Joern release
#   git                    -> some Joern workflows fetch code
# --no-install-recommends keeps the image small.
# Deleting the apt cache in the SAME RUN keeps that layer small too.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl ca-certificates unzip git \
    && rm -rf /var/lib/apt/lists/*

# Pinned Joern version (TODO: use a real tag from the releases page)
ARG JOERN_VERSION=v4.0.647

# Download and install Joern
WORKDIR /opt
RUN curl -fsSL "https://github.com/joernio/joern/releases/download/${JOERN_VERSION}/joern-install.sh" \
        -o joern-install.sh \
    && chmod +x joern-install.sh \
    && ./joern-install.sh \
        --install-dir=/opt/joern \
        --version="${JOERN_VERSION}" \
        --without-plugins \
    && rm joern-install.sh

# Make Joern commands available
ENV PATH="/opt/joern/joern-cli:${PATH}"

# Give the JVM a memory cap. Joern is memory-hungry; raise this for big repos.
# (Also make sure Docker Desktop itself is allowed enough RAM.)
ENV JAVA_OPTS="-Xmx4G"

# Your code is mounted here at runtime:
#   docker run --rm -v "$PWD/code:/workspace" shield-joern joern-parse .
WORKDIR /workspace

# Default command: open the interactive Joern shell.
CMD ["joern"]

# -------------------------------------------------------------
# DAY 2 TODO (to finish W1-P5-02):
#  - install Python (same version as the team) and the locked requirements
#  - install tree-sitter + grammars: python, c, cpp (java only if still in)
#  - add a smoke test: parse one sample per language (Joern + tree-sitter)
#  - run as a non-root user
#  - add a .dockerignore next to this file
# -------------------------------------------------------------
