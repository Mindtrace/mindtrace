# Dockerfile for pypylon runtime service
# This container provides complete Basler Pylon SDK functionality to host-based tests
# Supports both SDK testing and actual camera connections

# syntax=docker/dockerfile:1
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
# Optional: ensure GenTL search path is set (usually not needed on deb installs, but harmless)
ENV GENICAM_GENTL64_PATH=/opt/pylon/lib64

# System deps required by Pylon; also tools handy for debugging camera/network
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates wget tar xz-utils \
    libglx-mesa0 libgl1 libxcb-xinerama0 libxcb-xinput0 libxcb-cursor0 \
    udev usbutils iputils-ping net-tools ethtool \
    python3 python3-pip python3-dev \
 && rm -rf /var/lib/apt/lists/*

# Download + install Basler Pylon SDK DEBs (x86_64)
# Using official Basler SDK for complete functionality and hardware support
ARG PYLON_URL="https://github.com/Mindtrace/basler-sdk/releases/download/basler_sdk_linux/pylon-8.1.0_linux-x86_64_debs.tar.gz"
RUN mkdir -p /opt/pylon && \
    cd /opt/pylon && \
    wget -O pylon.tar.gz "$PYLON_URL" && \
    tar -xzf pylon.tar.gz && rm pylon.tar.gz && \
    # Install all .deb files found (pylon_* and codemeter*)
    apt-get update && \
    apt-get install -y ./pylon_*.deb ./codemeter*.deb || true && \
    # Fix any missing deps from dpkg stage
    apt-get -f install -y && \
    rm -rf /var/lib/apt/lists/* && \
    # Clean up the extracted debs to keep the image slim
    find /opt/pylon -maxdepth 1 -type f -name "*.deb" -delete

# Ensure ld cache is rebuilt—usually handled by deb postinst, but safe:
RUN ldconfig

# Install Python dependencies for the service
RUN python3 -m pip install --no-cache-dir \
    numpy \
    opencv-python-headless \
    pypylon

# Create service directory
RUN mkdir -p /tmp/pypylon

# Set working directory
WORKDIR /workspace

# Set environment variables
ENV PYTHONPATH=/workspace
ENV PYPYLON_SERVICE_MODE=true
ENV PYPYLON_AVAILABLE=true
ENV PYTHON=python3

# Expose the service socket directory
VOLUME ["/tmp/pypylon"]

# Health check to verify both Pylon SDK and pypylon are working
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python3 -c "from pypylon import pylon, genicam; factory = pylon.TlFactory.GetInstance(); print('Pylon SDK OK')"

# Default command - will be overridden in docker-compose
CMD ["python3", "-m", "tests.utils.pypylon.service"] 
